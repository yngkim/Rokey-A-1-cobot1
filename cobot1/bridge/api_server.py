"""ROS2 태스크 ↔ 웹앱 HTTP/WebSocket 브릿지 (care_server 없이 직접 실행)."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

from cobot1.bridge.task_session import WebTaskSession
from cobot1.bridge.voice_config import load_voice_config
from cobot1.bridge.voice_intent import (
    VoiceCommand,
    get_chain_task_ids,
    get_speech,
    get_voice_catalog,
    resolve_voice_command,
)
from cobot1.robot_config import ROBOT_ID
from cobot1.task_runner import TASK_REGISTRY, _ensure_registry

TASK_CATALOG: list[dict[str, str]] = [
    {"id": "prepare_medication", "label": "약 준비하기", "icon": "💊", "group": "복약"},
    {"id": "place_on_charger", "label": "충전기에 놓기", "icon": "📲", "group": "스마트폰"},
    {"id": "pick_from_charger", "label": "충전기에서 가져오기", "icon": "🔋", "group": "스마트폰"},
    {"id": "go_home", "label": "기본 위치 복귀", "icon": "🏠", "group": "제어"},
]

TASK_IDS = {task["id"] for task in TASK_CATALOG}


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

        self.create_subscription(String, "cobot1/status", self._on_status, 10)
        self.create_subscription(String, "cobot1/safety_alert", self._on_alert, 10)

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

    def refresh_robot_ready(self) -> bool:
        self._robot_ready = self._robot_mode_client.wait_for_service(timeout_sec=0.5)
        return self._robot_ready

    def _is_terminal_status(self, payload: dict[str, Any]) -> bool:
        state = payload.get("state", "")
        step = payload.get("step", "")
        if step == "finish" and state == "done":
            return True
        if state in ("error", "stopped"):
            return True
        if step in ("safe_abort", "user_stop") and state in (
            "error",
            "recovered",
            "critical",
        ):
            return True
        return False

    def _should_release_busy(self, payload: dict[str, Any]) -> bool:
        """체인 중간 finish/done 은 busy 유지, 정지·오류는 즉시 해제."""
        if not self._is_terminal_status(payload):
            return False
        state = payload.get("state", "")
        step = payload.get("step", "")
        if state in ("stopped", "error"):
            return True
        if step in ("safe_abort", "user_stop") and state in (
            "error",
            "recovered",
            "critical",
        ):
            return True
        if step == "finish" and state == "done":
            return not self._chain_active
        return not self._chain_active

    def _on_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            payload = {"message": msg.data}
        self._last_status = payload
        state = payload.get("state", "")
        step = payload.get("step", "")
        if payload.get("task"):
            with self._task_lock:
                self._current_task_id = payload["task"]
        with self._task_lock:
            if self._should_release_busy(payload):
                self._busy = False
                rel_state = payload.get("state", "")
                rel_step = payload.get("step", "")
                if rel_state in ("stopped", "error") or not self._chain_active:
                    self._chain_active = False
                    self._chain_abort = False
                    self._current_task_id = ""
                    self._voice_command_id = ""
                elif rel_step == "finish" and rel_state == "done":
                    self._current_task_id = ""
                    self._voice_command_id = ""
            elif state == "running":
                self._busy = True
        self._broadcast({"type": "status", "data": payload})

    def _on_alert(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            payload = {"message": msg.data}
        self._last_alert = payload
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
                "busy": self._busy,
                "current_task": self._current_task_id,
                "last_status": self._last_status,
            }
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

    def reset_and_home(self) -> dict[str, Any]:
        """SAFE_STOP 해제 → 세션 정리 → 홈 복귀 (백그라운드 스레드).

        정상 상태에서 호출하면 SAFE_STOP 해제를 건너뛰고 바로 홈 복귀한다.
        busy 중이면 stop 요청 후 1 초 대기하고 진행한다.
        """
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

        def _worker():
            success = False
            try:
                success = self._execute_task("go_home")
            except Exception as exc:
                self.get_logger().error(f"홈 복귀 실패: {exc}")
            finally:
                with self._task_lock:
                    self._busy = False
                    self._current_task_id = ""
                self._broadcast(
                    {"type": "task_complete", "data": {"task": "go_home", "success": success}}
                )

        threading.Thread(target=_worker, name="cobot1_reset_home", daemon=True).start()
        return {
            "success": True,
            "message": "SAFE_STOP 해제 후 홈 복귀를 시작합니다.",
            "code": "STARTED",
        }

    def _execute_task(self, task_id: str) -> bool:
        return self._task_session.run(task_id)

    def shutdown_session(self) -> None:
        self._task_session.cleanup()

    def stop_task(self) -> dict[str, Any]:
        with self._task_lock:
            if not self._busy:
                return {
                    "success": False,
                    "message": "실행 중인 작업이 없습니다.",
                    "code": "NOT_RUNNING",
                }
            self._chain_abort = True
            self._chain_active = False
            task_id = self._current_task_id or self._task_session.current_task
        stopped = self._task_session.request_stop()
        self._schedule_stop_watchdog(task_id)
        return {
            "success": stopped,
            "message": "작업을 중단하고 기본 위치로 복귀합니다.",
            "code": "STOPPING",
        }

    def _schedule_stop_watchdog(self, task_id: str) -> None:
        """정지 후에도 busy 가 풀리지 않을 때 UI·상태 강제 해제."""

        def _watch() -> None:
            deadline = time.time() + 90.0
            while time.time() < deadline:
                with self._task_lock:
                    if not self._busy:
                        return
                time.sleep(1.0)
            self.get_logger().warning(
                "정지 watchdog: busy 강제 해제 (task=%s)" % task_id
            )
            with self._task_lock:
                if not self._busy:
                    return
                self._busy = False
                self._chain_active = False
                self._chain_abort = False
                self._current_task_id = ""
                self._voice_command_id = ""
            self._broadcast(
                {
                    "type": "task_complete",
                    "data": {
                        "task": task_id,
                        "success": False,
                        "aborted": True,
                    },
                }
            )

        threading.Thread(
            target=_watch,
            name="cobot1_stop_watchdog",
            daemon=True,
        ).start()

    def _speech_payload(self, command_id: str, phase: str) -> dict[str, str]:
        if phase == "not_understood":
            text = get_speech("global", "not_understood")
        elif phase == "busy":
            text = get_speech("global", "busy")
        elif phase == "error":
            text = get_speech("global", "error")
        else:
            text = get_speech(command_id, phase)
        return {"text": text, "phase": phase}

    def handle_voice_command(self, text: str) -> dict[str, Any]:
        command = resolve_voice_command(text)
        if command is None:
            return {
                "matched": False,
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
            if self._busy:
                return {
                    "matched": True,
                    "command_id": command.id,
                    "action": "rejected",
                    "speech": self._speech_payload("global", "busy"),
                    "success": False,
                    "message": "다른 작업이 실행 중입니다.",
                    "code": "BUSY",
                }

        if command.action == "run_chain":
            return self._start_task_chain(command)

        return {
            "matched": True,
            "command_id": command.id,
            "action": "rejected",
            "speech": self._speech_payload("global", "error"),
            "success": False,
            "message": f"지원하지 않는 음성 동작: {command.action}",
            "code": "UNSUPPORTED",
        }

    def _start_task_chain(self, command: VoiceCommand) -> dict[str, Any]:
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
            self._busy = True
            self._chain_active = True
            self._chain_abort = False
            self._voice_command_id = command.id
            self._current_task_id = command.id

        task_ids = command.task_ids
        label = self._voice_labels.get(command.id, command.id)

        def _worker():
            success = True
            failed_task = ""
            aborted = False
            try:
                for task_id in task_ids:
                    with self._task_lock:
                        if self._chain_abort:
                            success = False
                            failed_task = task_id
                            aborted = True
                            break
                    if not self._execute_task(task_id):
                        success = False
                        failed_task = task_id
                        break
            except Exception as exc:
                success = False
                self.get_logger().error(f"음성 체인 {command.id} 실패: {exc}")
            finally:
                with self._task_lock:
                    self._busy = False
                    self._chain_active = False
                    self._chain_abort = False
                    self._current_task_id = ""
                    self._voice_command_id = ""
                self._broadcast(
                    {
                        "type": "task_complete",
                        "data": {
                            "task": failed_task or task_ids[-1],
                            "success": success,
                            "voice_command_id": command.id,
                            "chain": True,
                            "aborted": aborted,
                        },
                    }
                )

        threading.Thread(
            target=_worker,
            name=f"cobot1_voice_{command.id}",
            daemon=True,
        ).start()

        return {
            "matched": True,
            "command_id": command.id,
            "action": "started",
            "speech": self._speech_payload(command.id, "ack"),
            "success": True,
            "message": f"{label} 실행을 시작했습니다.",
            "code": "STARTED",
        }

    def start_task(self, task_id: str) -> dict[str, Any]:
        if task_id not in TASK_IDS:
            return {
                "success": False,
                "message": f"알 수 없는 작업: {task_id}",
                "code": "NOT_FOUND",
            }

        if task_id == "prepare_medication":
            with self._task_lock:
                if self._busy:
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
            result = self._start_task_chain(command)
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
            elif self._busy:
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

        def _worker():
            success = False
            try:
                success = self._execute_task(task_id)
            except Exception as exc:
                self.get_logger().error(f"태스크 {task_id} 실패: {exc}")
            finally:
                with self._task_lock:
                    self._busy = False
                    self._current_task_id = ""
                self._broadcast(
                    {
                        "type": "task_complete",
                        "data": {"task": task_id, "success": success},
                    }
                )

        threading.Thread(
            target=_worker,
            name=f"cobot1_web_{task_id}",
            daemon=True,
        ).start()

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
    더 최신 index.html 이 있는 쪽을 사용합니다.
    """
    from pathlib import Path

    source = Path(__file__).resolve().parents[3] / "web" / "dist"
    installed: Path | None = None
    try:
        from ament_index_python.packages import get_package_share_directory

        share = Path(get_package_share_directory("cobot1"))
        candidate = share / "web" / "dist"
        if candidate.is_dir():
            installed = candidate
    except Exception:
        pass

    def _index_mtime(path: Path) -> float:
        index = path / "index.html"
        return index.stat().st_mtime if index.is_file() else 0.0

    if source.is_dir() and installed is not None:
        if _index_mtime(source) >= _index_mtime(installed):
            return source
        return installed
    if installed is not None:
        return installed
    if source.is_dir():
        return source
    return Path()


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
            response = await super().get_response(path, scope)
            req_path = scope.get("path", "")
            if req_path in ("", "/") or path in ("", "index.html"):
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


def create_app():
    try:
        from contextlib import asynccontextmanager

        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel
        from starlette.routing import WebSocketRoute
        from starlette.websockets import WebSocket, WebSocketDisconnect
    except ImportError as exc:
        raise ImportError(
            "FastAPI가 필요합니다: pip install fastapi uvicorn[standard]"
        ) from exc

    from pathlib import Path

    class VoiceCommandRequest(BaseModel):
        text: str

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
            "busy": bridge._busy,
            "current_task": bridge._current_task_id,
            "current_task_label": label,
            "current_step": bridge._last_status.get("step", ""),
            "robot_namespace": ROBOT_ID,
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
    def run_task(task_id: str):
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        result = bridge.start_task(task_id)
        if result.get("code") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        return result

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
                "busy": bridge._busy,
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
        with bridge._task_lock:
            bridge._busy = False
            bridge._chain_active = False
            bridge._chain_abort = False
            bridge._current_task_id = ""
            bridge._voice_command_id = ""
        bridge._broadcast(
            {
                "type": "task_complete",
                "data": {"task": "", "success": False, "forced_idle": True},
            }
        )
        return {"ok": True, "message": "화면 잠금을 해제했습니다."}

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
