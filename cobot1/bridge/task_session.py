"""웹 API용 지속 DSR 세션 (노드 재생성 없이 태스크 반복 실행)."""

from __future__ import annotations

import copy
import threading

from cobot1.bridge.handoff_gate import ensure_handoff_gate
from cobot1.bridge.safety_decision_gate import ensure_safety_decision_gate
from cobot1.config_loader import load_scenarios
from cobot1.motion.primitives import MotionContext, RobotMotion
from cobot1.robot_init import destroy_dsr_node, prepare_autonomous_mode, setup
from cobot1.task_runner import TASK_REGISTRY, _ensure_registry


class WebTaskSession:
    """DSR 노드를 유지하며 태스크를 반복 실행합니다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._motion: RobotMotion | None = None
        self._current_task: str = ""
        self._running = False
        self._last_result_code: str = "OK"

    @property
    def last_result_code(self) -> str:
        return self._last_result_code

    @property
    def current_task(self) -> str:
        return self._current_task

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def _ensure_motion(self) -> RobotMotion:
        if self._motion is not None:
            return self._motion

        node = setup("care_web_dsr")
        prepare_autonomous_mode()
        scenarios = load_scenarios()
        self._motion = RobotMotion(
            MotionContext(
                node=node,
                motion_cfg=scenarios["motion"],
                gripper_cfg=scenarios["gripper"],
                safety_cfg=scenarios.get("safety", {}),
            )
        )
        return self._motion

    def run(self, task_id: str, care_user_id: str | None = None) -> bool:
        _ensure_registry()
        ensure_handoff_gate()
        ensure_safety_decision_gate()
        if task_id not in TASK_REGISTRY:
            raise ValueError(f"알 수 없는 태스크: {task_id}")

        with self._lock:
            if self._running:
                return False
            self._running = True
            self._current_task = task_id
            motion = self._ensure_motion()
            prepare_autonomous_mode()
            scenarios = load_scenarios()
            if care_user_id:
                scenarios = copy.deepcopy(scenarios)
                for key in ("serve_meal", "return_tray", "measure_tray_weight"):
                    if key in scenarios:
                        scenarios[key] = {
                            **scenarios[key],
                            "care_user_id": care_user_id,
                        }
            task = TASK_REGISTRY[task_id](scenarios, motion)

        try:
            result = task.run()
            motion.clear_cancel()
            self._last_result_code = result.code
            return result.success
        finally:
            with self._lock:
                self._running = False
                self._current_task = ""

    def request_stop(self) -> bool:
        # self._lock 을 획득하지 않는다: run()이 lock을 점유한 채 실행 중일 때
        # lock 을 기다리면 데드락이 발생해 정지 신호가 태스크 종료 후에야 전달된다.
        # CPython GIL 하에서 객체 참조 읽기는 원자적이므로 안전하다.
        motion = self._motion
        if motion is None:
            return False
        motion.request_stop(self._current_task or "motion")
        return True

    def force_abort(self) -> None:
        """정지·강제 idle 시 세션 실행 플래그 및 motion 취소 상태를 해제."""
        self.request_stop()
        motion = self._motion
        if motion is not None:
            motion.clear_cancel()
            motion.safety.clear_external_force_violation()
        with self._lock:
            self._running = False
            self._current_task = ""

    def cleanup(self) -> None:
        with self._lock:
            self._running = False
            self._current_task = ""
            if self._motion is not None:
                self._motion.shutdown()
                self._motion = None
            destroy_dsr_node()
