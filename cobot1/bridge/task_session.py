"""웹 API용 지속 DSR 세션 (노드 재생성 없이 태스크 반복 실행)."""

from __future__ import annotations

import threading

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

    @property
    def current_task(self) -> str:
        return self._current_task

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

    def run(self, task_id: str) -> bool:
        _ensure_registry()
        if task_id not in TASK_REGISTRY:
            raise ValueError(f"알 수 없는 태스크: {task_id}")

        with self._lock:
            self._current_task = task_id
            motion = self._ensure_motion()
            prepare_autonomous_mode()
            scenarios = load_scenarios()
            task = TASK_REGISTRY[task_id](scenarios, motion)
            result = task.run()
            if not result.success:
                try:
                    motion.clear_cancel()
                    motion.recover_pose(task_id)
                except Exception as exc:
                    motion._node.get_logger().warn(f"실패 후 복귀: {exc}")
            return result.success

    def request_stop(self) -> bool:
        with self._lock:
            if self._motion is None:
                return False
            task = self._current_task or "motion"
            self._motion.request_stop(task)
            return True

    def cleanup(self) -> None:
        with self._lock:
            self._current_task = ""
            if self._motion is not None:
                self._motion.shutdown()
                self._motion = None
            destroy_dsr_node()
