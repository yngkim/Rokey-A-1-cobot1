"""태스크 실행 공통 러너."""

from __future__ import annotations

from typing import Any, Type

from cobot1.config_loader import load_scenarios
from cobot1.motion.primitives import MotionContext, RobotMotion
from cobot1.robot_init import destroy_dsr_node, prepare_autonomous_mode, setup
from cobot1.tasks.base import BaseTask, TaskResult


TASK_REGISTRY: dict[str, Type[BaseTask]] = {}


def register_task(task_cls: Type[BaseTask]) -> Type[BaseTask]:
    TASK_REGISTRY[task_cls.name] = task_cls
    return task_cls


def _ensure_registry() -> None:
    if TASK_REGISTRY:
        return
    from cobot1.tasks.close_bottle import CloseBottleTask
    from cobot1.tasks.go_home import GoHomeTask
    from cobot1.tasks.open_bottle import OpenBottleTask
    from cobot1.tasks.measure_tray_weight import MeasureTrayWeightTask
    from cobot1.tasks.pick_from_charger import PickFromChargerTask
    from cobot1.tasks.pick_place_pill import PickPlacePillTask
    from cobot1.tasks.place_on_charger import PlaceOnChargerTask
    from cobot1.tasks.pour_water import PourWaterTask

    for task_cls in (
        GoHomeTask,
        OpenBottleTask,
        CloseBottleTask,
        PourWaterTask,
        PickPlacePillTask,
        PlaceOnChargerTask,
        PickFromChargerTask,
        MeasureTrayWeightTask,
    ):
        register_task(task_cls)


def run_task(
    task_name: str,
    node_name: str | None = None,
    config_path: str | None = None,
    overrides: dict[str, Any] | None = None,
    args=None,
) -> TaskResult:
    _ensure_registry()
    if task_name not in TASK_REGISTRY:
        raise ValueError(f"알 수 없는 태스크: {task_name}")

    scenarios = load_scenarios(config_path, overrides)
    node = setup(node_name or f"cobot1_{task_name}", args=args)
    motion = None
    try:
        prepare_autonomous_mode()
        motion = RobotMotion(
            MotionContext(
                node=node,
                motion_cfg=scenarios["motion"],
                gripper_cfg=scenarios["gripper"],
                safety_cfg=scenarios.get("safety", {}),
            )
        )
        task = TASK_REGISTRY[task_name](scenarios, motion)
        result = task.run()
        if not result.success:
            try:
                motion.clear_cancel()
                motion.recover_pose(task_name)
            except Exception as exc:
                node.get_logger().warn(f"실패 후 복귀: {exc}")
        return result
    finally:
        if motion is not None:
            motion.shutdown()
        destroy_dsr_node()
