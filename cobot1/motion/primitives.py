"""재시도·안전 복귀가 포함된 공통 모션 프리미티브."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from rclpy.node import Node
from std_msgs.msg import String

from cobot1.motion.gripper import Gripper


class MotionError(RuntimeError):
    pass


@dataclass
class MotionContext:
    node: Node
    motion_cfg: dict
    gripper_cfg: dict
    status_topic: str = "cobot1/status"


class RobotMotion:
    def __init__(self, ctx: MotionContext):
        self._ctx = ctx
        self._node = ctx.node
        self._cfg = ctx.motion_cfg
        self._retry = int(self._cfg.get("retry_count", 1))
        self._status_pub = self._node.create_publisher(String, ctx.status_topic, 10)
        self._gripper = Gripper(self._node, ctx.gripper_cfg)
        self._import_motion_api()

    @property
    def gripper(self) -> Gripper:
        return self._gripper

    def _import_motion_api(self) -> None:
        from cobot1.motion.dsr_imports import import_dsr_api

        api = import_dsr_api()
        self.DR_BASE = api["DR_BASE"]
        self.DR_TOOL = api["DR_TOOL"]
        self.DR_MV_MOD_REL = api["DR_MV_MOD_REL"]
        self.movej = api["movej"]
        self.movel = api["movel"]
        self.mwait = api["mwait"]
        self.check_motion = api["check_motion"]
        self.posj = api["posj"]
        self.posx = api["posx"]
        self.trans = api["trans"]

    def publish_status(
        self,
        task: str,
        step: str,
        state: str,
        message: str = "",
        extra: dict | None = None,
    ) -> None:
        payload = {
            "task": task,
            "step": step,
            "state": state,
            "message": message,
            "timestamp": time.time(),
        }
        if extra:
            payload.update(extra)
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self._status_pub.publish(msg)
        self._node.get_logger().info(f"[{task}] {step} ({state}) {message}")

    def _run_with_retry(self, label: str, action: Callable[[], None]) -> None:
        last_error: Exception | None = None
        for attempt in range(self._retry + 1):
            try:
                action()
                self.mwait(0)
                if self.check_motion() != 0:
                    raise MotionError(f"{label}: 모션 완료 확인 실패")
                return
            except Exception as exc:
                last_error = exc
                self._node.get_logger().warn(
                    f"{label} 실패 (시도 {attempt + 1}/{self._retry + 1}): {exc}"
                )
                time.sleep(0.3)
        raise MotionError(f"{label} 최종 실패: {last_error}")

    def go_home(self, task: str = "motion") -> None:
        self.publish_status(task, "go_home", "running")
        home = self.posj(self._cfg["home_joint"])
        vel = self._cfg["joint_vel"]
        acc = self._cfg["joint_acc"]

        def _move():
            self.movej(home, vel=vel, acc=acc)

        self._run_with_retry("go_home", _move)
        self.publish_status(task, "go_home", "done")

    def move_task_pose(self, pose: Sequence[float], label: str, task: str) -> None:
        self.publish_status(task, label, "running")
        target = self.posx(list(pose))
        vel = self._cfg["task_vel"]
        acc = self._cfg["task_acc"]

        def _move():
            self.movel(target, vel=vel, acc=acc, ref=self.DR_BASE)

        self._run_with_retry(label, _move)
        self.publish_status(task, label, "done")

    def move_relative_tool(self, delta: Sequence[float], label: str, task: str) -> None:
        self.publish_status(task, label, "running")
        vel = self._cfg["task_vel"]
        acc = self._cfg["task_acc"]

        def _move():
            self.movel(
                list(delta),
                vel=vel,
                acc=acc,
                ref=self.DR_TOOL,
                mod=self.DR_MV_MOD_REL,
            )

        self._run_with_retry(label, _move)
        self.publish_status(task, label, "done")

    def approach_pose(
        self,
        pose: Sequence[float],
        height_mm: float,
        label: str,
        task: str,
    ) -> None:
        approach = self.trans(
            self.posx(list(pose)),
            [0.0, 0.0, float(height_mm), 0.0, 0.0, 0.0],
            self.DR_BASE,
            self.DR_BASE,
        )
        self.publish_status(task, label, "running")
        vel = self._cfg["task_vel"]
        acc = self._cfg["task_acc"]

        def _move():
            self.movel(approach, vel=vel, acc=acc, ref=self.DR_BASE)

        self._run_with_retry(label, _move)
        self.publish_status(task, label, "done")

    def retreat_z(self, height_mm: float, label: str, task: str) -> None:
        self.move_relative_tool(
            [0.0, 0.0, float(height_mm), 0.0, 0.0, 0.0],
            label,
            task,
        )

    def rotate_tool_z_steps(
        self,
        total_deg: float,
        steps: int,
        label_prefix: str,
        task: str,
    ) -> None:
        if steps <= 0:
            raise MotionError("twist_steps는 1 이상이어야 합니다")
        step_angle = total_deg / steps
        for index in range(steps):
            self.move_relative_tool(
                [0.0, 0.0, 0.0, 0.0, 0.0, step_angle],
                f"{label_prefix}_{index + 1}",
                task,
            )

    def safe_abort(self, task: str, reason: str) -> None:
        self.publish_status(task, "safe_abort", "error", reason)
        try:
            retreat = float(self._cfg.get("retreat_height_mm", 100))
            self.retreat_z(retreat, "safe_retreat", task)
            self.go_home(task)
        except Exception as exc:
            self.publish_status(task, "safe_abort", "critical", str(exc))

    def run_sequence(
        self,
        task: str,
        steps: Iterable[tuple[str, Callable[[], None]]],
    ) -> None:
        for step_name, step_action in steps:
            try:
                step_action()
            except Exception as exc:
                self.publish_status(task, step_name, "error", str(exc))
                self.safe_abort(task, str(exc))
                raise
