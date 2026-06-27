"""웹 API용 지속 DSR 세션 (노드 재생성 없이 태스크 반복 실행)."""

from __future__ import annotations

import copy
import threading

from cobot1.bridge.handoff_gate import ensure_handoff_gate
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

    def run(self, task_id: str, care_user_id: str | None = None) -> bool:
        _ensure_registry()
        ensure_handoff_gate()
        if task_id not in TASK_REGISTRY:
            raise ValueError(f"알 수 없는 태스크: {task_id}")

        with self._lock:
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
            result = task.run()
            # recover_pose 는 run_sequence → safe_abort 내부에서 이미 수행된다.
            # 여기서 다시 호출하면 두 번째 홈 복귀 status("running")가 재발행되어
            # 웹 UI busy 표시가 초기화되지 않는 버그가 생기므로 제거한다.
            motion.clear_cancel()
            return result.success

    def request_stop(self) -> bool:
        # self._lock 을 획득하지 않는다: run()이 lock을 점유한 채 실행 중일 때
        # lock 을 기다리면 데드락이 발생해 정지 신호가 태스크 종료 후에야 전달된다.
        # CPython GIL 하에서 객체 참조 읽기는 원자적이므로 안전하다.
        motion = self._motion
        if motion is None:
            return False
        motion.request_stop(self._current_task or "motion")
        return True

    def cleanup(self) -> None:
        with self._lock:
            self._current_task = ""
            if self._motion is not None:
                self._motion.shutdown()
                self._motion = None
            destroy_dsr_node()
