"""동작 중 안전 모니터링 및 비상 중단."""

from __future__ import annotations

import json
import math
import threading
import time
from typing import TYPE_CHECKING, Callable

from std_msgs.msg import String

from cobot1.motion.exceptions import SafetyViolation

if TYPE_CHECKING:
    from rclpy.node import Node

# DRFC system states
STATE_SAFE_STOP = 5
STATE_EMERGENCY_STOP = 6
STATE_SAFE_STOP2 = 9

UNSAFE_ROBOT_STATES = {
    STATE_SAFE_STOP: "SAFE_STOP",
    STATE_EMERGENCY_STOP: "EMERGENCY_STOP",
    STATE_SAFE_STOP2: "SAFE_STOP2",
}

DEFAULT_MESSAGES = {
    "external_force": (
        "외력이 감지되어 동작을 중단했습니다. "
        "환자·물체 접촉 여부를 확인한 뒤 로봇을 재시작해 주세요."
    ),
    "unsafe_robot_state": (
        "로봇이 안전 정지 상태입니다. "
        "티칭 팬던트에서 알람을 확인하고 복구 후 다시 시도해 주세요."
    ),
    "motion_failed": "모션 실행에 실패했습니다. 로봇 상태를 확인해 주세요.",
    "connection_error": "로봇 통신 오류가 발생했습니다. 연결 상태를 확인해 주세요.",
    "unknown_error": "예기치 않은 오류가 발생했습니다. 동작을 중단했습니다.",
}


class SafetyGuard:
    """동작 중 외력·로봇 상태를 감시하고 비상 중단합니다."""

    def __init__(self, node: Node, cfg: dict, publish_status: Callable[..., None]):
        self._node = node
        self._cfg = cfg
        self._publish_status = publish_status
        self._enabled = bool(cfg.get("enabled", True))
        self._interval = float(cfg.get("monitor_interval_sec", 0.1))
        self._torque_limit = float(cfg.get("external_torque_max_norm", 8.0))
        self._messages = {**DEFAULT_MESSAGES, **cfg.get("messages", {})}
        self._abort = threading.Event()
        self._violation: SafetyViolation | None = None
        self._thread: threading.Thread | None = None
        self._task = ""
        self._move_stop_client = None
        self._alert_pub = node.create_publisher(String, "cobot1/safety_alert", 10)
        self._import_api()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def is_aborted(self) -> bool:
        return self._abort.is_set()

    def _import_api(self) -> None:
        from cobot1.motion.dsr_imports import import_dsr_api

        api = import_dsr_api()
        self._get_external_torque = api["get_external_torque"]
        self._get_robot_state = api["get_robot_state"]
        self._get_last_alarm = api["get_last_alarm"]
        self._get_tool_force = api["get_tool_force"]

        from dsr_msgs2.srv import MoveStop

        self._move_stop_client = self._node.create_client(MoveStop, "motion/move_stop")
        self._move_stop_request = MoveStop.Request()

    def start(self, task: str) -> None:
        if not self._enabled:
            return
        self._task = task
        self._abort.clear()
        self._violation = None
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name=f"safety_monitor_{task}",
            daemon=True,
        )
        self._thread.start()
        self._publish_status(task, "safety_monitor", "running", "안전 감시 시작")

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._abort.set()
            self._thread.join(timeout=2.0)
        self._thread = None

    def check_or_raise(self) -> None:
        if self._violation is not None:
            raise self._violation
        if self._abort.is_set() and self._violation is None:
            raise SafetyViolation(
                "안전 감시 중단",
                code="SAFETY_ABORT",
                user_message=self._messages["unknown_error"],
            )

    def _monitor_loop(self) -> None:
        while not self._abort.is_set():
            try:
                self._check_external_torque()
                self._check_robot_state()
            except SafetyViolation as exc:
                self._trigger_abort(exc)
                break
            except Exception as exc:
                self._node.get_logger().warn(f"안전 감시 오류(계속): {exc}")
            time.sleep(self._interval)

    def _check_external_torque(self) -> None:
        torque = self._get_external_torque()
        if torque == -1 or not isinstance(torque, (list, tuple)):
            return
        norm = math.sqrt(sum(float(v) ** 2 for v in torque[:6]))
        if norm > self._torque_limit:
            raise SafetyViolation(
                f"외력 감지: |τ|={norm:.2f} > {self._torque_limit}",
                code="EXTERNAL_FORCE",
                user_message=self._messages["external_force"],
                detail={"external_torque": list(torque), "norm": norm},
            )

    def _check_robot_state(self) -> None:
        state = self._get_robot_state()
        if state == -1:
            return
        label = UNSAFE_ROBOT_STATES.get(state)
        if label:
            raise SafetyViolation(
                f"비정상 로봇 상태: {label} ({state})",
                code="UNSAFE_ROBOT_STATE",
                user_message=self._messages["unsafe_robot_state"],
                detail={"robot_state": state, "state_label": label},
            )

    def _trigger_abort(self, violation: SafetyViolation) -> None:
        self._violation = violation
        self._abort.set()
        self._publish_alert(violation)
        self._publish_status(
            self._task,
            "safety_abort",
            "error",
            violation.user_message,
            extra={"code": violation.code, "detail": violation.detail},
        )
        self._node.get_logger().error(
            f"[SAFETY] {violation.code}: {violation} | {violation.user_message}"
        )
        self._request_move_stop()

    def _request_move_stop(self) -> None:
        if self._move_stop_client is None:
            return
        if not self._move_stop_client.wait_for_service(timeout_sec=0.5):
            self._node.get_logger().warn("motion/move_stop 서비스 없음")
            return
        future = self._move_stop_client.call_async(self._move_stop_request)
        start = time.time()
        while not future.done() and time.time() - start < 2.0:
            time.sleep(0.05)

    def _publish_alert(self, violation: SafetyViolation) -> None:
        alarm = None
        try:
            alarm = self._get_last_alarm()
        except Exception:
            pass

        payload = {
            "level": "error",
            "code": violation.code,
            "message": violation.user_message,
            "technical": str(violation),
            "task": self._task,
            "detail": violation.detail,
            "last_alarm": str(alarm) if alarm is not None else "",
            "timestamp": time.time(),
        }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self._alert_pub.publish(msg)

    def get_last_alarm_text(self) -> str:
        try:
            alarm = self._get_last_alarm()
            return str(alarm) if alarm not in (-1, None) else ""
        except Exception:
            return ""
