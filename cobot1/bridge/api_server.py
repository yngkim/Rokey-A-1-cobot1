"""ROS2 태스크 ↔ 웹앱 HTTP/WebSocket 브릿지 (care_server 없이 직접 실행)."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

from pydantic import BaseModel

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

from cobot1.bridge.care_store import (
    EVENT_MEAL,
    EVENT_MEDICATION_PREPARE,
    EVENT_MEDICATION_TAKEN,
    get_care_store,
)
from cobot1.bridge.event_store import get_event_store
from cobot1.bridge.handoff_gate import UserHandoffGate, set_handoff_gate
from cobot1.bridge.safety_decision_gate import SafetyDecisionGate, set_safety_decision_gate
from cobot1.bridge.task_session import WebTaskSession
from cobot1.motion.safety import UNSAFE_ROBOT_STATES
from cobot1.bridge.voice_config import load_voice_config
from cobot1.bridge.voice_intent import (
    VoiceCommand,
    get_chain_task_ids,
    get_speech,
    get_voice_catalog,
    resolve_voice_command,
)
from cobot1.robot_config import ROBOT_ID
from cobot1.runtime_state import (
    PHONE_ON_CHARGER,
    PHONE_WITH_USER,
    TRAY_ON_STATION,
    TRAY_WITH_USER,
    can_pick_from_charger,
    can_place_on_charger,
    can_return_tray,
    can_serve_tray,
    get_phone_location,
    get_tray_location,
    set_phone_location,
    set_tray_location,
)
from cobot1.task_runner import TASK_REGISTRY, _ensure_registry

TASK_CATALOG: list[dict[str, str]] = [
    {"id": "prepare_medication", "label": "약 준비하기", "icon": "💊", "group": "복약"},
    {"id": "place_on_charger", "label": "핸드폰 가져다놓기", "icon": "📲", "group": "스마트폰"},
    {"id": "pick_from_charger", "label": "핸드폰 가져오기", "icon": "🔋", "group": "스마트폰"},
    {"id": "serve_meal", "label": "식사 가져오기", "icon": "🍱", "group": "식사"},
    {"id": "return_tray", "label": "식사 가져가기", "icon": "↩️", "group": "식사"},
    {"id": "clean_floor", "label": "청소하기", "icon": "🧹", "group": "케어"},
    {"id": "go_home", "label": "기본 위치 복귀", "icon": "🏠", "group": "제어"},
]

TASK_IDS = {task["id"] for task in TASK_CATALOG}

ROBOT_STATE_LABELS: dict[int, str] = {
    -1: "UNKNOWN",
    0: "DISCONNECTED",
    1: "INITIALIZING",
    2: "STANDBY",
    3: "SAFE_OFF",
    4: "TEACHING",
    5: "SAFE_STOP",
    6: "EMERGENCY_STOP",
    7: "HOMING",
    8: "AUTONOMOUS",
    9: "SAFE_STOP2",
}


class RosBridge(Node):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__("care_web_bridge", namespace=ROBOT_ID)
        self._loop = loop
        self._ws_clients: set[Any] = set()
        self._busy = False
        self._robot_ready = False
        self._current_task_id = ""
        self._task_lock = threading.Lock()
        self._task_session = WebTaskSession()
        self._last_status: dict[str, Any] = {}
        self._last_alert: dict[str, Any] | None = None
        self._chain_active = False
        self._chain_abort = False
        self._voice_command_id = ""
        self._voice_labels: dict[str, str] = load_voice_config().get("labels", {})
        self._events = get_event_store()
        self._care = get_care_store()
        self._active_care_user_id = self._default_care_user_id()
        self._maintenance_mode = False
        self._current_run_id: str | None = None
        self._active_worker: threading.Thread | None = None
        self._robot_state = -1
        self._robot_state_label = "UNKNOWN"
        self._handoff_gate = UserHandoffGate(on_change=self._broadcast_sync)
        set_handoff_gate(self._handoff_gate)
        self._safety_decision_gate = SafetyDecisionGate(on_change=self._broadcast_sync)
        set_safety_decision_gate(self._safety_decision_gate)

        self.create_subscription(String, "cobot1/status", self._on_status, 10)
        self.create_subscription(String, "cobot1/safety_alert", self._on_alert, 10)
        self.create_timer(2.0, self._poll_robot_state)

        from dsr_msgs2.srv import SetRobotControl, SetRobotMode

        self._robot_mode_client = self.create_client(
            SetRobotMode, "system/set_robot_mode"
        )
        self._robot_control_client = self.create_client(
            SetRobotControl, "system/set_robot_control"
        )
        self.refresh_robot_ready()
        self.get_logger().info(
            "care_web_bridge 준비 (namespace=%s, robot_ready=%s)"
            % (ROBOT_ID, self._robot_ready)
        )

    def _default_care_user_id(self) -> str:
        users = self._care.list_users()
        return users[0]["id"] if users else "patient_01"

    def set_active_care_user(self, user_id: str) -> dict[str, Any]:
        user = self._care.get_user(user_id)
        if user is None:
            return {
                "success": False,
                "message": "등록되지 않은 사용자입니다.",
                "code": "NOT_FOUND",
            }
        self._active_care_user_id = user_id
        return {"success": True, "user": user}

    def get_active_care_user(self) -> dict[str, Any]:
        user = self._care.get_user(self._active_care_user_id)
        if user is None:
            user = self._care.ensure_user(
                self._default_care_user_id(),
                "기본 사용자",
            )
            self._active_care_user_id = user["id"]
        return user

    def record_care_event(
        self,
        *,
        event_type: str,
        user_id: str | None = None,
        quantity: float = 1.0,
        unit: str = "dose",
        note: str | None = None,
        run_id: str | None = None,
        source: str = "web",
        detail: dict | None = None,
    ) -> dict[str, Any]:
        uid = user_id or self._active_care_user_id
        event = self._care.record_event(
            user_id=uid,
            event_type=event_type,
            quantity=quantity,
            unit=unit,
            note=note,
            run_id=run_id,
            source=source,
            detail=detail,
        )
        self.audit_action(
            "care_event",
            actor=source,
            detail={"user_id": uid, "event_type": event_type, "quantity": quantity},
        )
        return event

    def _log_prepare_medication_care(
        self,
        *,
        success: bool,
        user_id: str | None,
        run_id: str | None,
        source: str,
    ) -> None:
        if not success:
            return
        uid = user_id or self._active_care_user_id
        if not uid or self._care.get_user(uid) is None:
            return
        try:
            self.record_care_event(
                event_type=EVENT_MEDICATION_PREPARE,
                user_id=uid,
                quantity=1.0,
                unit="dose",
                note="로봇 약 준비 완료",
                run_id=run_id,
                source=source,
            )
        except Exception as exc:
            self.get_logger().warning(f"케어 기록 실패 (medication_prepare): {exc}")

    def refresh_robot_ready(self) -> bool:
        self._robot_ready = self._robot_mode_client.wait_for_service(timeout_sec=0.5)
        return self._robot_ready

    def _poll_robot_state(self) -> None:
        if not self._robot_ready:
            return
        try:
            from cobot1.motion.dsr_imports import import_dsr_api

            state = int(import_dsr_api()["get_robot_state"]())
        except Exception:
            return
        label = ROBOT_STATE_LABELS.get(state, UNSAFE_ROBOT_STATES.get(state, f"STATE_{state}"))
        if state != self._robot_state:
            self._robot_state = state
            self._robot_state_label = label
            self._broadcast(
                {
                    "type": "robot_state",
                    "data": {"state": state, "label": label},
                }
            )

    def _check_maintenance(self) -> dict[str, Any] | None:
        if self._maintenance_mode:
            return {
                "success": False,
                "message": "유지보수 모드 중입니다. 관리자에게 문의하세요.",
                "code": "MAINTENANCE",
            }
        return None

    def set_maintenance(self, enabled: bool, actor: str = "admin") -> None:
        self._maintenance_mode = enabled
        action = "maintenance_on" if enabled else "maintenance_off"
        self.audit_action(action, actor=actor, detail={"enabled": enabled})
        self._broadcast(
            {"type": "maintenance", "data": {"enabled": enabled}},
        )
        self._broadcast_sync()

    def audit_action(
        self,
        action: str,
        actor: str = "system",
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._events.audit(action, actor=actor, detail=detail)
        self._broadcast_audit(action, actor, detail or {})

    def _broadcast_audit(
        self,
        action: str,
        actor: str,
        detail: dict[str, Any],
    ) -> None:
        self._broadcast(
            {
                "type": "audit",
                "data": {
                    "action": action,
                    "actor": actor,
                    "detail": detail,
                    "timestamp": time.time(),
                },
            }
        )

    def _begin_run(
        self,
        task_id: str,
        trigger: str,
        voice_command_id: str | None = None,
    ) -> str:
        run_id = self._events.start_run(task_id, trigger, voice_command_id)
        with self._task_lock:
            self._current_run_id = run_id
        return run_id

    def _end_run(
        self,
        run_id: str | None,
        *,
        success: bool,
        code: str | None = None,
    ) -> None:
        if run_id:
            self._events.finish_run(run_id, success=success, code=code)
        with self._task_lock:
            if self._current_run_id == run_id:
                self._current_run_id = None

    def force_idle(self, actor: str = "user") -> dict[str, Any]:
        self.audit_action("force_idle", actor=actor)
        self._task_session.force_abort()
        self._wait_worker_or_cleanup()
        with self._task_lock:
            self._busy = False
            self._chain_active = False
            self._chain_abort = False
            self._current_task_id = ""
            self._voice_command_id = ""
            self._current_run_id = None
        self._handoff_gate.clear()
        self._safety_decision_gate.clear()
        self._broadcast(
            {
                "type": "task_complete",
                "data": {"task": "", "success": False, "forced_idle": True},
            }
        )
        self._broadcast_sync()
        return {"ok": True, "message": "화면 잠금을 해제했습니다."}

    def _is_execution_blocked(self) -> bool:
        return self._busy or self._task_session.is_running()

    def _task_complete_data(
        self,
        task_id: str,
        success: bool,
        *,
        result_code: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"task": task_id, "success": success, **extra}
        if not success:
            data["code"] = result_code or self._task_session.last_result_code
        return data

    def _launch_worker(self, target, name: str) -> threading.Thread:
        def _run() -> None:
            try:
                target()
            finally:
                with self._task_lock:
                    if self._active_worker is thread:
                        self._active_worker = None

        thread = threading.Thread(target=_run, name=name, daemon=True)
        with self._task_lock:
            self._active_worker = thread
        thread.start()
        return thread

    def _wait_worker_or_cleanup(self, timeout_sec: float = 3.0) -> None:
        with self._task_lock:
            worker = self._active_worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=timeout_sec)
        if self._task_session.is_running():
            self.get_logger().warning(
                "force_idle: worker still active after %.1fs — resetting DSR session"
                % timeout_sec
            )
            try:
                self._task_session.cleanup()
            except Exception as exc:
                self.get_logger().error(f"force_idle session cleanup failed: {exc}")

    def _broadcast_sync(self) -> None:
        with self._task_lock:
            sync = {
                "busy": self._is_execution_blocked(),
                "session_running": self._task_session.is_running(),
                "current_task": self._current_task_id,
                "last_status": self._last_status,
                "maintenance": self._maintenance_mode,
                "phone_location": get_phone_location(),
                "tray_location": get_tray_location(),
            }
            sync.update(self._handoff_gate.snapshot())
            sync.update(self._safety_decision_gate.snapshot())
        self._broadcast({"type": "sync", "data": sync})

    def _is_terminal_status(self, payload: dict[str, Any]) -> bool:
        state = payload.get("state", "")
        step = payload.get("step", "")
        if step == "finish" and state == "done":
            return True
        if step == "user_stop" and state in ("recovered", "error", "critical"):
            return True
        if step == "safe_abort" and state in ("recovered", "error", "critical"):
            return True
        if state == "error" and step not in ("user_stop", "safe_abort"):
            return True
        return False

    def _should_release_busy(self, payload: dict[str, Any]) -> bool:
        """user_stop/safe_abort 복구는 worker finally 에서 busy 해제. status 는 UI 표시용."""
        if not self._is_terminal_status(payload):
            return False
        state = payload.get("state", "")
        step = payload.get("step", "")
        if step == "user_stop" and state in ("recovered", "error", "critical"):
            return False
        if step == "safe_abort" and state in ("recovered", "error", "critical"):
            return False
        if step == "finish" and state == "done":
            return not self._chain_active
        if state == "error" and step not in ("user_stop", "safe_abort"):
            return True
        return False

    def _on_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            payload = {"message": msg.data}
        self._last_status = payload
        with self._task_lock:
            run_id = self._current_run_id
        try:
            self._events.record_status(payload, run_id=run_id)
        except Exception as exc:
            self.get_logger().warning(f"status 이벤트 저장 실패: {exc}")
        state = payload.get("state", "")
        step = payload.get("step", "")
        if payload.get("task"):
            with self._task_lock:
                if self._busy:
                    self._current_task_id = payload["task"]
        with self._task_lock:
            prev_blocked = self._is_execution_blocked()
            if self._should_release_busy(payload):
                self._busy = False
                rel_step = payload.get("step", "")
                rel_state = payload.get("state", "")
                if rel_step == "finish" and rel_state == "done":
                    self._current_task_id = ""
                    self._voice_command_id = ""
            blocked = self._is_execution_blocked()
        self._broadcast({"type": "status", "data": payload})
        if payload.get("code") == "OBJECT_MISSING":
            from cobot1.motion.grasp_verify import user_feedback_message

            speech_text = payload.get("speech_text") or user_feedback_message()
            self._broadcast(
                {
                    "type": "object_missing",
                    "data": {
                        "code": "OBJECT_MISSING",
                        "message": speech_text,
                        "speech_text": speech_text,
                        "object_id": payload.get("object_id", ""),
                        "object_label": payload.get("object_label", ""),
                        "task": payload.get("task", ""),
                        "step": payload.get("step", ""),
                    },
                }
            )
        if prev_blocked != blocked:
            self._broadcast_sync()

    def _on_alert(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            payload = {"message": msg.data}
        self._last_alert = payload
        try:
            self._events.record_alert(payload)
        except Exception as exc:
            self.get_logger().warning(f"안전 알람 저장 실패: {exc}")
        self._broadcast({"type": "safety_alert", "data": payload})

    def _broadcast(self, message: dict) -> None:
        if not self._ws_clients:
            return
        text = json.dumps(message, ensure_ascii=False)

        def _send():
            dead = set()
            for ws in self._ws_clients:
                try:
                    asyncio.run_coroutine_threadsafe(ws.send_text(text), self._loop)
                except Exception:
                    dead.add(ws)
            self._ws_clients -= dead

        self._loop.call_soon_threadsafe(_send)

    def register_ws(self, ws) -> None:
        self._ws_clients.add(ws)
        with self._task_lock:
            sync = {
                "busy": self._is_execution_blocked(),
                "session_running": self._task_session.is_running(),
                "current_task": self._current_task_id,
                "last_status": self._last_status,
                "maintenance": self._maintenance_mode,
                "phone_location": get_phone_location(),
                "tray_location": get_tray_location(),
            }
            sync.update(self._handoff_gate.snapshot())
            sync.update(self._safety_decision_gate.snapshot())
        asyncio.run_coroutine_threadsafe(
            ws.send_text(
                json.dumps({"type": "sync", "data": sync}, ensure_ascii=False)
            ),
            self._loop,
        )
        if self._last_alert:
            asyncio.run_coroutine_threadsafe(
                ws.send_text(
                    json.dumps({"type": "safety_alert", "data": self._last_alert}, ensure_ascii=False)
                ),
                self._loop,
            )

    def unregister_ws(self, ws) -> None:
        self._ws_clients.discard(ws)

    def _reset_safe_stop(self) -> bool:
        """SAFE_STOP(5) 또는 SAFE_OFF(3) 상태에서 STANDBY로 복귀 요청.

        SetRobotControl 서비스를 직접 호출한다. 이미 ROS executor가 별도
        스레드에서 spin 중이므로 future.done() 폴링으로 완료를 기다린다.
        """
        from dsr_msgs2.srv import SetRobotControl

        if not self._robot_control_client.wait_for_service(timeout_sec=3.0):
            self.get_logger().warning("SetRobotControl 서비스 없음")
            return False

        for control_code, label in [(2, "SAFE_STOP→STANDBY"), (3, "SAFE_OFF→STANDBY")]:
            req = SetRobotControl.Request()
            req.robot_control = control_code
            future = self._robot_control_client.call_async(req)

            deadline = time.time() + 5.0
            while not future.done() and time.time() < deadline:
                time.sleep(0.05)

            if future.done():
                result = future.result()
                if result is not None and result.success:
                    self.get_logger().info(f"로봇 상태 해제 성공 ({label})")
                    return True

        self.get_logger().warning("SetRobotControl 두 코드 모두 실패 — 이미 정상 상태이거나 복구 불가")
        return False

    def reset_and_home(self, actor: str = "user") -> dict[str, Any]:
        """SAFE_STOP 해제 → 세션 정리 → 홈 복귀 (백그라운드 스레드).

        정상 상태에서 호출하면 SAFE_STOP 해제를 건너뛰고 바로 홈 복귀한다.
        busy 중이면 stop 요청 후 1 초 대기하고 진행한다.
        """
        self.audit_action("reset", actor=actor)
        self._reset_safe_stop()  # 이미 정상이면 no-op (실패해도 계속 진행)

        with self._task_lock:
            if self._busy:
                self._task_session.request_stop()
                self._busy = False
                self._current_task_id = ""
                time.sleep(0.5)

        self._task_session.cleanup()

        _ensure_registry()
        if "go_home" not in TASK_REGISTRY:
            return {
                "success": False,
                "message": "go_home 태스크가 등록되지 않았습니다.",
                "code": "NOT_FOUND",
            }

        with self._task_lock:
            self._busy = True
            self._current_task_id = "go_home"

        run_id = self._begin_run("go_home", "admin")

        def _worker():
            success = False
            try:
                success = self._execute_task("go_home")
            except Exception as exc:
                self.get_logger().error(f"홈 복귀 실패: {exc}")
            finally:
                self._end_run(run_id, success=success)
                with self._task_lock:
                    self._busy = False
                    self._current_task_id = ""
                self._broadcast(
                    {"type": "task_complete", "data": {"task": "go_home", "success": success}}
                )
                self._broadcast_sync()

        threading.Thread(target=_worker, name="cobot1_reset_home", daemon=True).start()
        return {
            "success": True,
            "message": "SAFE_STOP 해제 후 홈 복귀를 시작합니다.",
            "code": "STARTED",
        }

    def _execute_task(self, task_id: str, user_id: str | None = None) -> bool:
        uid = user_id or self._active_care_user_id
        return self._task_session.run(task_id, care_user_id=uid)

    def shutdown_session(self) -> None:
        self._task_session.cleanup()

    def stop_task(self, actor: str = "user") -> dict[str, Any]:
        self.audit_action("stop", actor=actor)
        with self._task_lock:
            if not self._is_execution_blocked():
                if actor == "admin":
                    self.force_idle(actor=actor)
                    return {
                        "success": True,
                        "message": "실행 중인 작업이 없어 사용자 화면 잠금을 해제했습니다.",
                        "code": "FORCED_IDLE",
                    }
                return {
                    "success": False,
                    "message": "실행 중인 작업이 없습니다.",
                    "code": "NOT_RUNNING",
                }
            self._chain_abort = True
            self._chain_active = False
            task_id = self._current_task_id or self._task_session.current_task
        stopped = self._task_session.request_stop()
        self._safety_decision_gate.clear()
        self._schedule_stop_watchdog(task_id, actor=actor)
        self._broadcast_sync()
        return {
            "success": stopped,
            "message": "작업을 중단하고 기본 위치로 복귀합니다.",
            "code": "STOPPING",
        }

    def _schedule_stop_watchdog(self, task_id: str, actor: str = "user") -> None:
        """정지 후에도 busy 가 풀리지 않을 때 UI·상태 강제 해제."""
        timeout_sec = 30.0

        def _watch() -> None:
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                if not self._is_execution_blocked():
                    self._broadcast_sync()
                    return
                time.sleep(1.0)
            self.get_logger().warning(
                "정지 watchdog: busy 강제 해제 (task=%s, actor=%s)" % (task_id, actor)
            )
            self.force_idle(actor=actor)

        threading.Thread(
            target=_watch,
            name="cobot1_stop_watchdog",
            daemon=True,
        ).start()

    def _speech_payload(self, command_id: str, phase: str) -> dict[str, str]:
        global_phases = (
            "not_understood",
            "busy",
            "error",
            "phone_with_user",
            "phone_on_charger",
        )
        if phase in global_phases:
            text = get_speech("global", phase)
        else:
            text = get_speech(command_id, phase)
        return {"text": text, "phase": phase}

    def _phone_task_rejection(self, task_id: str) -> dict[str, str] | None:
        if task_id == "pick_from_charger" and not can_pick_from_charger():
            return {
                "message": get_speech("global", "phone_with_user"),
                "code": "PHONE_WITH_USER",
                "speech_phase": "phone_with_user",
            }
        if task_id == "place_on_charger" and not can_place_on_charger():
            return {
                "message": get_speech("global", "phone_on_charger"),
                "code": "PHONE_ON_CHARGER",
                "speech_phase": "phone_on_charger",
            }
        return None

    def _tray_task_rejection(self, task_id: str) -> dict[str, str] | None:
        if task_id == "serve_meal" and not can_serve_tray():
            return {
                "message": "트레이가 원위치에 없습니다.",
                "code": "TRAY_NOT_ON_STATION",
            }
        if task_id == "return_tray" and not can_return_tray():
            return {
                "message": "트레이가 원위치에 없습니다.",
                "code": "TRAY_NOT_ON_STATION",
            }
        return None

    def _apply_phone_task_result(self, task_id: str) -> None:
        if task_id == "pick_from_charger":
            set_phone_location(PHONE_WITH_USER)
        elif task_id == "place_on_charger":
            set_phone_location(PHONE_ON_CHARGER)
        else:
            return
        self._broadcast_sync()

    def _apply_tray_task_result(self, task_id: str) -> None:
        if task_id in ("serve_meal", "return_tray"):
            set_tray_location(TRAY_ON_STATION)
        else:
            return
        self._broadcast_sync()

    def confirm_handoff(self, action: str) -> dict[str, Any]:
        action = action.strip().lower()
        if action not in ("tray_return",):
            return {
                "success": False,
                "message": "action은 tray_return 이어야 합니다.",
                "code": "INVALID_ACTION",
            }
        with self._task_lock:
            if not self._busy:
                return {
                    "success": False,
                    "message": "실행 중인 작업이 없습니다.",
                    "code": "NOT_BUSY",
                }
        ok, message = self._handoff_gate.try_confirm(action)
        if not ok:
            return {
                "success": False,
                "message": message,
                "code": "NOT_WAITING",
            }
        self._broadcast_sync()
        return {
            "success": True,
            "message": message,
            "code": "CONFIRMED",
            "action": action,
        }

    def confirm_safety_decision(self, action: str) -> dict[str, Any]:
        if action not in ("resume", "abort", "home"):
            return {
                "success": False,
                "message": "action은 resume, abort, home 중 하나여야 합니다.",
                "code": "INVALID_ACTION",
            }
        with self._task_lock:
            if not self._busy:
                return {
                    "success": False,
                    "message": "실행 중인 작업이 없습니다.",
                    "code": "NOT_BUSY",
                }
        ok, message = self._safety_decision_gate.decide(action)
        if not ok:
            return {
                "success": False,
                "message": message,
                "code": "NOT_WAITING",
            }
        self._broadcast_sync()
        return {
            "success": True,
            "message": message,
            "code": "DECIDED",
            "action": action,
        }

    def handle_voice_command(self, text: str) -> dict[str, Any]:
        command = resolve_voice_command(text)
        if command is None:
            return {
                "matched": False,
                "heard_text": text,
                "speech": self._speech_payload("global", "not_understood"),
                "code": "NOT_MATCHED",
            }

        if command.action == "stop":
            ack = self._speech_payload(command.id, "ack")
            stop_result = self.stop_task()
            return {
                "matched": True,
                "command_id": command.id,
                "action": "stop",
                "speech": ack,
                "success": stop_result.get("success", False),
                "message": stop_result.get("message", ""),
                "code": stop_result.get("code", "STOPPING"),
            }

        with self._task_lock:
            if self._is_execution_blocked():
                return {
                    "matched": True,
                    "command_id": command.id,
                    "action": "rejected",
                    "speech": self._speech_payload("global", "busy"),
                    "success": False,
                    "message": "다른 작업이 실행 중입니다.",
                    "code": "BUSY",
                }

        blocked = self._check_maintenance()
        if blocked:
            return {
                "matched": True,
                "command_id": command.id,
                "action": "rejected",
                "speech": self._speech_payload("global", "error"),
                "success": False,
                "message": blocked["message"],
                "code": blocked["code"],
            }

        if command.action == "run_chain":
            return self._start_task_chain(command, trigger="voice")

        if command.action == "run_task":
            task_id = command.task_id
            if not task_id:
                return {
                    "matched": True,
                    "command_id": command.id,
                    "action": "rejected",
                    "speech": self._speech_payload("global", "error"),
                    "success": False,
                    "message": "실행할 작업이 지정되지 않았습니다.",
                    "code": "INVALID_TASK",
                }
            phone_block = self._phone_task_rejection(task_id)
            if phone_block:
                return {
                    "matched": True,
                    "command_id": command.id,
                    "action": "rejected",
                    "speech": self._speech_payload(
                        "global", phone_block["speech_phase"]
                    ),
                    "success": False,
                    "message": phone_block["message"],
                    "code": phone_block["code"],
                }
            return self._start_voice_task(command)

        return {
            "matched": True,
            "command_id": command.id,
            "action": "rejected",
            "speech": self._speech_payload("global", "error"),
            "success": False,
            "message": f"지원하지 않는 음성 동작: {command.action}",
            "code": "UNSUPPORTED",
        }

    def _start_voice_task(self, command: VoiceCommand) -> dict[str, Any]:
        task_id = command.task_id
        if not self.refresh_robot_ready():
            return {
                "matched": True,
                "command_id": command.id,
                "action": "rejected",
                "speech": self._speech_payload("global", "error"),
                "success": False,
                "message": (
                    "로봇 제어 서비스에 연결되지 않았습니다. "
                    "bringup을 실행하고 SERVO ON 상태인지 확인하세요."
                ),
                "code": "NO_ROBOT",
            }

        _ensure_registry()
        if task_id not in TASK_REGISTRY:
            return {
                "matched": True,
                "command_id": command.id,
                "action": "rejected",
                "speech": self._speech_payload("global", "error"),
                "success": False,
                "message": f"등록되지 않은 작업: {task_id}",
                "code": "NOT_FOUND",
            }

        tray_block = self._tray_task_rejection(task_id)
        if tray_block:
            return {
                "matched": True,
                "command_id": command.id,
                "action": "rejected",
                "speech": self._speech_payload("global", "tray_not_on_station"),
                "success": False,
                "message": tray_block["message"],
                "code": tray_block["code"],
            }

        with self._task_lock:
            self._busy = True
            self._chain_active = False
            self._chain_abort = False
            self._voice_command_id = command.id
            self._current_task_id = task_id

        label = self._voice_labels.get(command.id, task_id)
        self.audit_action(
            "task_start",
            actor="voice",
            detail={"task_id": task_id, "voice_command_id": command.id},
        )
        run_id = self._begin_run(task_id, "voice", voice_command_id=command.id)

        def _worker():
            success = False
            try:
                success = self._execute_task(task_id)
            except Exception as exc:
                self.get_logger().error(f"음성 태스크 {task_id} 실패: {exc}")
            finally:
                if success:
                    self._apply_phone_task_result(task_id)
                    self._apply_tray_task_result(task_id)
                self._end_run(
                    run_id,
                    success=success,
                    code=None if success else self._task_session.last_result_code,
                )
                with self._task_lock:
                    self._busy = False
                    self._current_task_id = ""
                    self._voice_command_id = ""
                self._broadcast(
                    {
                        "type": "task_complete",
                        "data": self._task_complete_data(
                            task_id,
                            success,
                            voice_command_id=command.id,
                        ),
                    }
                )
                self._broadcast_sync()

        self._launch_worker(_worker, name=f"cobot1_voice_{command.id}")

        return {
            "matched": True,
            "command_id": command.id,
            "task_id": task_id,
            "action": "started",
            "speech": self._speech_payload(command.id, "ack"),
            "success": True,
            "message": f"{label} 실행을 시작했습니다.",
            "code": "STARTED",
        }

    def _start_task_chain(
        self,
        command: VoiceCommand,
        *,
        trigger: str = "voice",
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if not command.task_ids:
            return {
                "matched": True,
                "command_id": command.id,
                "action": "rejected",
                "speech": self._speech_payload("global", "error"),
                "success": False,
                "message": "연속 실행할 작업이 없습니다.",
                "code": "INVALID_CHAIN",
            }

        if not self.refresh_robot_ready():
            return {
                "matched": True,
                "command_id": command.id,
                "action": "rejected",
                "speech": self._speech_payload("global", "error"),
                "success": False,
                "message": (
                    "로봇 제어 서비스에 연결되지 않았습니다. "
                    "bringup을 실행하고 SERVO ON 상태인지 확인하세요."
                ),
                "code": "NO_ROBOT",
            }

        blocked = self._check_maintenance()
        if blocked:
            return {
                "matched": True,
                "command_id": command.id,
                "action": "rejected",
                "speech": self._speech_payload("global", "error"),
                "success": False,
                "message": blocked["message"],
                "code": blocked["code"],
            }

        _ensure_registry()
        for task_id in command.task_ids:
            if task_id not in TASK_REGISTRY:
                return {
                    "matched": True,
                    "command_id": command.id,
                    "action": "rejected",
                    "speech": self._speech_payload("global", "error"),
                    "success": False,
                    "message": f"등록되지 않은 작업: {task_id}",
                    "code": "NOT_FOUND",
                }

        with self._task_lock:
            if self._is_execution_blocked():
                return {
                    "matched": True,
                    "command_id": command.id,
                    "action": "rejected",
                    "speech": self._speech_payload("global", "busy"),
                    "success": False,
                    "message": "다른 작업이 실행 중입니다.",
                    "code": "BUSY",
                }

        with self._task_lock:
            self._busy = True
            self._chain_active = True
            self._chain_abort = False
            self._voice_command_id = command.id
            self._current_task_id = command.id

        task_ids = command.task_ids
        label = self._voice_labels.get(command.id, command.id)
        care_user_id = user_id or self._active_care_user_id

        self.audit_action(
            "task_start",
            actor=trigger,
            detail={
                "task_id": command.id,
                "chain": task_ids,
                "user_id": care_user_id,
            },
        )

        def _worker():
            success = True
            failed_task = ""
            aborted = False
            last_run_id: str | None = None
            fail_code = "TASK_FAILED"
            try:
                for task_id in task_ids:
                    with self._task_lock:
                        if self._chain_abort:
                            success = False
                            failed_task = task_id
                            aborted = True
                            break
                    run_id = self._begin_run(
                        task_id, trigger, voice_command_id=command.id
                    )
                    last_run_id = run_id
                    task_ok = self._execute_task(task_id, user_id=care_user_id)
                    self._end_run(
                        run_id,
                        success=task_ok,
                        code=None if task_ok else self._task_session.last_result_code,
                    )
                    if not task_ok:
                        success = False
                        failed_task = task_id
                        fail_code = self._task_session.last_result_code
                        break
                    self._apply_phone_task_result(task_id)
                    self._apply_tray_task_result(task_id)
            except Exception as exc:
                success = False
                self.get_logger().error(f"음성 체인 {command.id} 실패: {exc}")
            finally:
                if command.id == "prepare_medication":
                    self._log_prepare_medication_care(
                        success=success,
                        user_id=care_user_id,
                        run_id=last_run_id,
                        source=trigger,
                    )
                with self._task_lock:
                    self._busy = False
                    self._chain_active = False
                    self._chain_abort = False
                    self._current_task_id = ""
                    self._voice_command_id = ""
                self._broadcast(
                    {
                        "type": "task_complete",
                        "data": self._task_complete_data(
                            failed_task or task_ids[-1],
                            success,
                            result_code=None if success else fail_code,
                            voice_command_id=command.id,
                            chain=True,
                            aborted=aborted,
                        ),
                    }
                )
                self._broadcast_sync()

        self._launch_worker(_worker, name=f"cobot1_voice_{command.id}")

        return {
            "matched": True,
            "command_id": command.id,
            "action": "started",
            "speech": self._speech_payload(command.id, "ack"),
            "success": True,
            "message": f"{label} 실행을 시작했습니다.",
            "code": "STARTED",
        }

    def start_task(self, task_id: str, user_id: str | None = None) -> dict[str, Any]:
        if task_id not in TASK_IDS:
            return {
                "success": False,
                "message": f"알 수 없는 작업: {task_id}",
                "code": "NOT_FOUND",
            }

        blocked = self._check_maintenance()
        if blocked:
            return blocked

        phone_block = self._phone_task_rejection(task_id)
        if phone_block:
            return {
                "success": False,
                "message": phone_block["message"],
                "code": phone_block["code"],
            }

        tray_block = self._tray_task_rejection(task_id)
        if tray_block:
            return {
                "success": False,
                "message": tray_block["message"],
                "code": tray_block["code"],
            }

        if task_id == "prepare_medication":
            with self._task_lock:
                if self._is_execution_blocked():
                    return {
                        "success": False,
                        "message": "다른 작업이 실행 중입니다. 완료 후 다시 시도해 주세요.",
                        "code": "BUSY",
                    }
            chain_ids = get_chain_task_ids("prepare_medication")
            if not chain_ids:
                return {
                    "success": False,
                    "message": "약 준비하기 작업 순서가 설정되지 않았습니다.",
                    "code": "INVALID_CHAIN",
                }
            command = VoiceCommand(
                id="prepare_medication",
                phrase="",
                action="run_chain",
                task_ids=chain_ids,
            )
            result = self._start_task_chain(
                command,
                trigger="web",
                user_id=user_id,
            )
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "code": result.get("code", "STARTED"),
                "task": "prepare_medication",
                "chain": True,
            }

        with self._task_lock:
            if self._busy and task_id == "go_home":
                self._task_session.request_stop()
                time.sleep(1.0)
                self._busy = False
                self._current_task_id = ""
            elif self._is_execution_blocked():
                return {
                    "success": False,
                    "message": "다른 작업이 실행 중입니다. 완료 후 다시 시도해 주세요.",
                    "code": "BUSY",
                }
            if not self.refresh_robot_ready():
                return {
                    "success": False,
                    "message": (
                        "로봇 제어 서비스에 연결되지 않았습니다. "
                        "bringup을 실행하고 SERVO ON 상태인지 확인하세요."
                    ),
                    "code": "NO_ROBOT",
                }
            _ensure_registry()
            if task_id not in TASK_REGISTRY:
                return {
                    "success": False,
                    "message": f"등록되지 않은 작업: {task_id}",
                    "code": "NOT_FOUND",
                }
            self._busy = True
            self._chain_abort = False
            self._current_task_id = task_id

        label = next((t["label"] for t in TASK_CATALOG if t["id"] == task_id), task_id)
        self.audit_action("task_start", actor="web", detail={"task_id": task_id})
        run_id = self._begin_run(task_id, "web")

        def _worker():
            success = False
            try:
                success = self._execute_task(task_id, user_id=user_id)
            except Exception as exc:
                self.get_logger().error(f"태스크 {task_id} 실패: {exc}")
            finally:
                if success:
                    self._apply_phone_task_result(task_id)
                    self._apply_tray_task_result(task_id)
                self._end_run(
                    run_id,
                    success=success,
                    code=None if success else self._task_session.last_result_code,
                )
                with self._task_lock:
                    self._busy = False
                    self._current_task_id = ""
                self._broadcast(
                    {
                        "type": "task_complete",
                        "data": self._task_complete_data(task_id, success),
                    }
                )
                self._broadcast_sync()

        self._launch_worker(_worker, name=f"cobot1_web_{task_id}")

        return {
            "success": True,
            "message": f"{label} 실행을 시작했습니다 (ros2 run cobot1 {task_id})",
            "code": "STARTED",
        }


_ros_node: RosBridge | None = None
_ros_executor: MultiThreadedExecutor | None = None
_ros_thread: threading.Thread | None = None


def start_ros(loop: asyncio.AbstractEventLoop) -> RosBridge:
    global _ros_node, _ros_executor, _ros_thread
    if _ros_node is not None:
        return _ros_node

    if not rclpy.ok():
        rclpy.init()
    _ros_node = RosBridge(loop)
    _ros_executor = MultiThreadedExecutor()
    _ros_executor.add_node(_ros_node)

    def _spin():
        _ros_executor.spin()

    _ros_thread = threading.Thread(target=_spin, name="ros_spin", daemon=True)
    _ros_thread.start()
    return _ros_node


def get_ros_node() -> RosBridge:
    if _ros_node is None:
        raise RuntimeError("ROS bridge not started")
    return _ros_node


def _web_dist_dir():
    """설치(share) 또는 개발(소스) 경로에서 web/dist 를 찾습니다.

    npm run build 직후 colcon build 를 안 하면 install 쪽 dist 가 오래될 수 있으므로
    후보 경로 중 index.html 이 가장 최신인 디렉터리를 사용합니다.
    """
    from pathlib import Path

    here = Path(__file__).resolve()
    candidates: list[Path] = []

    try:
        from ament_index_python.packages import get_package_share_directory

        share = Path(get_package_share_directory("cobot1"))
        candidates.append(share / "web" / "dist")
    except Exception:
        pass

    # 소스 트리 (cobot1/cobot1/bridge → cobot1/web/dist)
    pkg_dist = here.parents[2] / "web" / "dist"
    if pkg_dist.is_dir():
        candidates.append(pkg_dist)

    # 워크스페이스 src/cobot1/web/dist (ros2 run 시 install 경로에서도 탐색)
    for ancestor in here.parents:
        src_dist = ancestor / "src" / "cobot1" / "web" / "dist"
        if src_dist.is_dir():
            candidates.append(src_dist)
            break
        if (ancestor / "web" / "dist").is_dir() and (ancestor / "package.xml").is_file():
            candidates.append(ancestor / "web" / "dist")
            break

    def _index_mtime(path: Path) -> float:
        index = path / "index.html"
        return index.stat().st_mtime if index.is_file() else 0.0

    best: Path | None = None
    best_mtime = -1.0
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve())
        if key in seen or not path.is_dir():
            continue
        seen.add(key)
        mtime = _index_mtime(path)
        if mtime > best_mtime:
            best_mtime = mtime
            best = path

    return best if best is not None else Path()


def _mount_web_ui(app, dist) -> None:
    """SPA 정적 파일. /api/* 요청은 정적 서버가 405로 막지 않도록 선제 처리."""
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import JSONResponse
    from starlette.routing import Match, Mount
    from starlette.types import Receive, Scope, Send

    class HTTPOnlyMount(Mount):
        """WebSocket(/ws)이 정적 Mount에 잡혀 403 나는 것 방지."""

        def matches(self, scope):
            if scope["type"] != "http":
                return Match.NONE, {}
            return super().matches(scope)

    class SPAStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                response = await super().get_response(path, scope)
            except Exception as exc:
                from starlette.exceptions import HTTPException as StarletteHTTPException

                status = getattr(exc, "status_code", None)
                if self.html and status == 404:
                    response = await super().get_response("index.html", scope)
                else:
                    raise
            req_path = scope.get("path", "")
            if req_path in ("", "/") or path in ("", "index.html"):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            elif req_path.startswith("/admin"):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return response

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                return
            if scope.get("path", "").startswith("/api/"):
                response = JSONResponse(
                    {
                        "detail": (
                            "API 엔드포인트를 찾을 수 없습니다. "
                            "colcon build 후 care_web_api를 재시작하세요."
                        )
                    },
                    status_code=404,
                )
                await response(scope, receive, send)
                return
            await super().__call__(scope, receive, send)

    static = SPAStaticFiles(directory=str(dist), html=True)
    app.router.routes.append(HTTPOnlyMount("/", app=static, name="static"))


class VoiceCommandRequest(BaseModel):
    text: str


class TaskRunRequest(BaseModel):
    user_id: str | None = None


class HandoffConfirmRequest(BaseModel):
    action: str


class SafetyDecisionRequest(BaseModel):
    action: str


class ActiveCareUserRequest(BaseModel):
    user_id: str


class CareEventRequest(BaseModel):
    event_type: str
    user_id: str | None = None
    quantity: float = 1.0
    unit: str = "dose"
    note: str | None = None
    detail: dict | None = None


def create_app():
    try:
        from contextlib import asynccontextmanager

        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from starlette.routing import WebSocketRoute
        from starlette.websockets import WebSocket, WebSocketDisconnect
    except ImportError as exc:
        raise ImportError(
            "FastAPI가 필요합니다: pip install fastapi uvicorn[standard]"
        ) from exc

    from pathlib import Path

    bridge_holder: dict[str, RosBridge] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()
        bridge_holder["bridge"] = start_ros(loop)
        get_ros_node().get_logger().info(
            "Voice API: POST /api/voice/command, GET /api/voice/catalog"
        )
        yield
        bridge = bridge_holder.get("bridge")
        if bridge is not None:
            bridge.shutdown_session()
        if _ros_executor is not None:
            _ros_executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()

    app = FastAPI(title="Cobot1 Care API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            return {
                "ok": False,
                "api_ok": False,
                "robot_ready": False,
                "busy": False,
                "maintenance": False,
                "robot_namespace": ROBOT_ID,
            }
        robot_ready = bridge.refresh_robot_ready()
        if bridge._voice_command_id:
            label = bridge._voice_labels.get(
                bridge._voice_command_id,
                bridge._voice_command_id,
            )
        else:
            label = next(
                (t["label"] for t in TASK_CATALOG if t["id"] == bridge._current_task_id),
                bridge._current_task_id,
            )
        return {
            "ok": True,
            "api_ok": True,
            "robot_ready": robot_ready,
            "busy": bridge._is_execution_blocked(),
            "session_running": bridge._task_session.is_running(),
            "maintenance": bridge._maintenance_mode,
            "current_task": bridge._current_task_id,
            "current_task_label": label,
            "current_step": bridge._last_status.get("step", ""),
            "robot_namespace": ROBOT_ID,
            "phone_location": get_phone_location(),
            "phone_pick_available": can_pick_from_charger(),
            "phone_place_available": can_place_on_charger(),
            "tray_location": get_tray_location(),
            "tray_serve_available": can_serve_tray(),
            "tray_return_available": can_return_tray(),
            "handoff_action": bridge._handoff_gate.snapshot().get("handoff_action"),
            "handoff_prompt": bridge._handoff_gate.snapshot().get("handoff_prompt"),
            **bridge._safety_decision_gate.snapshot(),
        }

    @app.get("/api/tasks")
    def list_tasks():
        return {"tasks": TASK_CATALOG}

    @app.get("/api/voice/catalog")
    def voice_catalog():
        return get_voice_catalog()

    @app.post("/api/voice/command")
    def voice_command(body: VoiceCommandRequest):
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text가 필요합니다")
        return bridge.handle_voice_command(text)

    @app.post("/api/tasks/{task_id}")
    def run_task(task_id: str, body: TaskRunRequest | None = None):
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        user_id = body.user_id if body else None
        result = bridge.start_task(task_id, user_id=user_id)
        if result.get("code") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        if result.get("code") == "MAINTENANCE":
            raise HTTPException(status_code=503, detail=result["message"])
        return result

    @app.post("/api/handoff/confirm")
    def handoff_confirm(body: HandoffConfirmRequest):
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        result = bridge.confirm_handoff(body.action)
        if not result.get("success"):
            code = result.get("code", "ERROR")
            status = 409 if code == "NOT_WAITING" else 400
            raise HTTPException(status_code=status, detail=result.get("message"))
        return result

    @app.post("/api/safety/decision")
    def safety_decision(body: SafetyDecisionRequest):
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        result = bridge.confirm_safety_decision(body.action)
        if not result.get("success"):
            code = result.get("code", "ERROR")
            status = 409 if code == "NOT_WAITING" else 400
            raise HTTPException(status_code=status, detail=result.get("message"))
        return result

    @app.get("/api/care/users")
    def care_users():
        return {"users": get_care_store().list_users()}

    @app.get("/api/care/active-user")
    def care_active_user():
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        return {"user": bridge.get_active_care_user()}

    @app.post("/api/care/active-user")
    def care_set_active_user(body: ActiveCareUserRequest):
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        result = bridge.set_active_care_user(body.user_id)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("message"))
        return result

    @app.post("/api/care/events")
    def care_record_event(body: CareEventRequest):
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        if body.event_type not in (
            EVENT_MEDICATION_TAKEN,
            EVENT_MEAL,
        ):
            raise HTTPException(status_code=400, detail="지원하지 않는 이벤트 유형입니다")
        unit = body.unit
        if body.event_type == EVENT_MEAL and unit == "dose":
            unit = "serving"
        event = bridge.record_care_event(
            event_type=body.event_type,
            user_id=body.user_id,
            quantity=body.quantity,
            unit=unit,
            note=body.note,
            source="web",
            detail=body.detail,
        )
        return {"ok": True, "event": event}

    @app.post("/api/stop")
    def stop_task():
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        return bridge.stop_task()

    @app.post("/api/reset")
    def reset_robot():
        """SAFE_STOP 해제 후 홈 위치로 복귀. 안전 정지 이후 복구에 사용."""
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        return bridge.reset_and_home()

    @app.post("/api/sync")
    def force_sync():
        """UI stuck 시 busy 상태를 서버 기준으로 다시 맞춤 (강제 해제는 하지 않음)."""
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        bridge.refresh_robot_ready()
        with bridge._task_lock:
            payload = {
                "busy": bridge._is_execution_blocked(),
                "session_running": bridge._task_session.is_running(),
                "current_task": bridge._current_task_id,
                "last_status": bridge._last_status,
            }
        return {"ok": True, **payload}

    @app.post("/api/force_idle")
    def force_idle():
        """정지 후 UI가 실행 중에 멈춘 경우 busy 강제 해제 (로봇 동작은 별도 확인)."""
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        return bridge.force_idle(actor="user")

    from cobot1.bridge.admin_routes import register_admin_routes

    register_admin_routes(app, bridge_holder)

    async def care_websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            await websocket.close(code=1013, reason="ROS bridge 초기화 중")
            return
        bridge.register_ws(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            bridge.unregister_ws(websocket)

    app.router.routes.append(
        WebSocketRoute("/ws", endpoint=care_websocket_endpoint, name="care_ws")
    )

    dist = _web_dist_dir()
    if dist.is_dir():
        _mount_web_ui(app, dist)

    return app


def main():
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
