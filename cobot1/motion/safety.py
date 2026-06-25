"""동작 중 안전 모니터링 및 비상 중단."""

from __future__ import annotations

import json
import math
import threading
import time
from typing import TYPE_CHECKING, Callable

from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import Float64MultiArray, String

from cobot1.motion.exceptions import SafetyViolation
from cobot1.robot_config import ROBOT_ID

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
    """동작 중 외력·로봇 상태를 감시하고 비상 중단합니다.

    DSR_ROBOT2는 동일 노드에서 spin_until_future_complete를 중복 호출할 수 없으므로,
    외력 감시는 별도 노드의 토픽 구독으로 처리하고 로봇 상태는 메인 스레드에서만 조회합니다.
    """

    def __init__(self, node: Node, cfg: dict, publish_status: Callable[..., None]):
        self._node = node
        self._cfg = cfg
        self._publish_status = publish_status
        self._enabled = bool(cfg.get("enabled", True))
        self._interval = float(cfg.get("monitor_interval_sec", 0.1))
        self._torque_limit = float(cfg.get("external_torque_max_norm", 30.0))
        self._messages = {**DEFAULT_MESSAGES, **cfg.get("messages", {})}
        self._abort = threading.Event()
        self._violation: SafetyViolation | None = None
        self._thread: threading.Thread | None = None
        self._task = ""
        self._alert_pub = node.create_publisher(String, "cobot1/safety_alert", 10)

        self._latest_tool_force: list[float] | None = None
        self._force_lock = threading.Lock()
        self._monitor_node = None
        self._executor: SingleThreadedExecutor | None = None
        self._spin_thread: threading.Thread | None = None
        self._move_stop_client = None
        self._move_stop_request = None
        self._get_robot_state = None
        self._get_last_alarm = None
        self._force_abort_paused = False
        self._state_check_paused = False
        self._contact_search_depth = 0

        if self._enabled:
            self._setup_monitor_node()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def is_aborted(self) -> bool:
        return self._abort.is_set()

    def _setup_monitor_node(self) -> None:
        import rclpy
        from dsr_msgs2.srv import MoveStop

        from cobot1.motion.dsr_imports import import_dsr_api

        api = import_dsr_api()
        self._get_robot_state = api["get_robot_state"]
        self._get_last_alarm = api["get_last_alarm"]

        self._monitor_node = rclpy.create_node(
            "cobot1_safety_monitor",
            namespace=ROBOT_ID,
        )
        group = MutuallyExclusiveCallbackGroup()
        self._monitor_node.create_subscription(
            Float64MultiArray,
            "msg/tool_force",
            self._on_tool_force,
            10,
            callback_group=group,
        )
        self._move_stop_client = self._monitor_node.create_client(
            MoveStop,
            "motion/move_stop",
            callback_group=group,
        )
        self._move_stop_request = MoveStop.Request()

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._monitor_node)
        self._spin_thread = threading.Thread(
            target=self._executor.spin,
            name="cobot1_safety_spin",
            daemon=True,
        )
        self._spin_thread.start()

    def _on_tool_force(self, msg: Float64MultiArray) -> None:
        with self._force_lock:
            self._latest_tool_force = list(msg.data)

    def pause_force_abort(self) -> None:
        """접촉 탐색 등 — 외력 초과 시 태스크 중단을 일시 해제."""
        self.begin_contact_search()

    def resume_force_abort(self) -> None:
        self.end_contact_search()

    def begin_contact_search(self) -> None:
        """접촉 탐색 모드: 외력·로봇 상태 안전 중단을 일시 해제."""
        self._contact_search_depth += 1
        self._force_abort_paused = True
        self._state_check_paused = True
        if self._violation is not None and self._violation.code in (
            "EXTERNAL_FORCE",
            "UNSAFE_ROBOT_STATE",
        ):
            self._violation = None
            self._abort.clear()

    def end_contact_search(self) -> None:
        self._contact_search_depth = max(0, self._contact_search_depth - 1)
        if self._contact_search_depth == 0:
            self._force_abort_paused = False
            self._state_check_paused = False

    def read_tool_force_vector(self) -> list[float]:
        """현재 tool force/torque 6축."""
        try:
            from cobot1.motion.dsr_imports import import_dsr_api

            api = import_dsr_api()
            force = api["get_tool_force"](ref=api["DR_BASE"])
            if force and force != -1 and len(force) >= 6:
                return [float(v) for v in force[:6]]
        except Exception:
            pass

        with self._force_lock:
            torque = self._latest_tool_force
        if torque and len(torque) >= 6:
            return [float(v) for v in torque[:6]]
        return [0.0] * 6

    def sample_force_baseline(
        self,
        samples: int = 8,
        interval_sec: float = 0.05,
    ) -> list[float]:
        """하강 전 힘 벡터 평균 (그리퍼 닫힌 상태 기준선)."""
        count = max(1, int(samples))
        acc = [0.0] * 6
        for _ in range(count):
            vec = self.read_tool_force_vector()
            for i in range(6):
                acc[i] += vec[i]
            time.sleep(interval_sec)
        return [v / count for v in acc]

    def read_tool_force_norm(self) -> float:
        """현재 tool force 벡터 노름."""
        vec = self.read_tool_force_vector()
        return math.sqrt(sum(v * v for v in vec))

    def contact_force_metric(
        self,
        baseline: list[float],
        *,
        z_only: bool = True,
        use_delta: bool = True,
    ) -> float:
        """접촉 판정용 힘 지표 (Z축 또는 전체 노름)."""
        current = self.read_tool_force_vector()
        if z_only:
            value = current[2] - baseline[2] if use_delta else current[2]
            return abs(value)
        if use_delta:
            return math.sqrt(
                sum((current[i] - baseline[i]) ** 2 for i in range(6))
            )
        return math.sqrt(sum(v * v for v in current))

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
        self._abort.set()
        self._contact_search_depth = 0
        self._force_abort_paused = False
        self._state_check_paused = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def shutdown(self) -> None:
        self.stop()
        if self._executor is not None:
            self._executor.shutdown()
            self._executor = None
        if self._spin_thread and self._spin_thread.is_alive():
            self._spin_thread.join(timeout=2.0)
        self._spin_thread = None
        if self._monitor_node is not None:
            self._monitor_node.destroy_node()
            self._monitor_node = None

    def check_or_raise(self) -> None:
        if self._violation is not None:
            raise self._violation
        if self._abort.is_set() and self._violation is None:
            raise SafetyViolation(
                "안전 감시 중단",
                code="SAFETY_ABORT",
                user_message=self._messages["unknown_error"],
            )
        if self._enabled and not self._state_check_paused:
            self._check_robot_state()

    def _monitor_loop(self) -> None:
        while not self._abort.is_set():
            try:
                self._check_external_torque_from_topic()
            except SafetyViolation as exc:
                self._trigger_abort(exc)
                break
            except Exception as exc:
                self._node.get_logger().warn(f"안전 감시 오류(계속): {exc}")
            time.sleep(self._interval)

    def _check_external_torque_from_topic(self) -> None:
        if self._force_abort_paused:
            return
        with self._force_lock:
            torque = self._latest_tool_force
        if not torque or len(torque) < 6:
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
        if self._get_robot_state is None:
            return
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
        if self._force_abort_paused:
            return
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

    def request_move_stop(self) -> None:
        self._request_move_stop()

    def _request_move_stop(self) -> None:
        if self._move_stop_client is None:
            return
        if not self._move_stop_client.service_is_ready():
            self._node.get_logger().warn("motion/move_stop 서비스 없음")
            return
        future = self._move_stop_client.call_async(self._move_stop_request)
        start = time.time()
        while not future.done() and time.time() - start < 2.0:
            time.sleep(0.05)

    def _publish_alert(self, violation: SafetyViolation) -> None:
        payload = {
            "level": "error",
            "code": violation.code,
            "message": violation.user_message,
            "technical": str(violation),
            "task": self._task,
            "detail": violation.detail,
            "last_alarm": "",
            "timestamp": time.time(),
        }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self._alert_pub.publish(msg)

    def get_last_alarm_text(self) -> str:
        if self._get_last_alarm is None:
            return ""
        try:
            alarm = self._get_last_alarm()
            return str(alarm) if alarm not in (-1, None) else ""
        except Exception:
            return ""
