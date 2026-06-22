"""태스크 실행 공통 러너."""

from __future__ import annotations

from typing import Any, Type

from cobot1.config_loader import load_scenarios
from cobot1.motion.primitives import MotionContext, RobotMotion
from cobot1.robot_init import prepare_autonomous_mode, setup
from cobot1.tasks.base import BaseTask, TaskResult


TASK_REGISTRY: dict[str, Type[BaseTask]] = {}


def register_task(task_cls: Type[BaseTask]) -> Type[BaseTask]:
    TASK_REGISTRY[task_cls.name] = task_cls
    return task_cls


def _ensure_registry() -> None:
    if TASK_REGISTRY:
        return
    from cobot1.tasks.insert_straw import InsertStrawTask
    from cobot1.tasks.open_bottle import OpenBottleTask
    from cobot1.tasks.pick_place_pill import PickPlacePillTask
    from cobot1.tasks.pull_place_tissue import PullPlaceTissueTask
    from cobot1.tasks.pour_water import PourWaterTask
    from cobot1.tasks.turn_off_switch import TurnOffSwitchTask

    for task_cls in (
        OpenBottleTask,
        PourWaterTask,
        PickPlacePillTask,
        InsertStrawTask,
        TurnOffSwitchTask,
        PullPlaceTissueTask,
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
    prepare_autonomous_mode()

    motion = RobotMotion(
        MotionContext(
            node=node,
            motion_cfg=scenarios["motion"],
            gripper_cfg=scenarios["gripper"],
        )
    )
    task = TASK_REGISTRY[task_name](scenarios, motion)
    return task.run()
