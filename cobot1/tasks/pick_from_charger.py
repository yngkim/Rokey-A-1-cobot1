"""스마트폰을 무선충전기에서 가져와 사용자에게 인수인계."""

from __future__ import annotations

from cobot1.motion.nudge_handoff import (
    confirm_phone_grasped,
    grip_phone,
    wait_for_external_force,
)
from cobot1.tasks.base import BaseTask


class PickFromChargerTask(BaseTask):
    name = "pick_from_charger"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        motion.set_recovery_joint(home_joint)

        approach_j5_joint = list(cfg["charger_approach_j5_joint"])
        approach_j4_joint = list(cfg["charger_approach_j4_joint"])
        prepose_joint = list(cfg["charger_approach_prepose_joint"])
        grasp_joint = list(cfg["charger_grasp_joint"])
        handoff_joint = list(cfg["user_handoff_joint"])

        grip_force = float(cfg["grip_force"])
        grasp_settle = float(cfg.get("grip_settle_sec", 3.0))
        home_vel = float(cfg.get("home_joint_vel", 12.0))
        home_acc = float(cfg.get("home_joint_acc", 12.0))
        approach_vel = float(cfg.get("approach_joint_vel", 12.0))
        approach_acc = float(cfg.get("approach_joint_acc", 12.0))
        carry_vel = float(cfg.get("carry_joint_vel", approach_vel))
        carry_acc = float(cfg.get("carry_joint_acc", approach_acc))
        grasp_approach_vel = float(cfg.get("charger_grasp_approach_joint_vel", 5.0))
        grasp_approach_acc = float(cfg.get("charger_grasp_approach_joint_acc", 5.0))
        grasp_tcp_z_advance_mm = float(cfg.get("charger_grasp_tcp_z_advance_mm", 5.0))
        grasp_advance_vel = list(cfg.get("charger_grasp_advance_vel", [8, 5]))
        grasp_advance_acc = list(cfg.get("charger_grasp_advance_acc", [16, 8]))
        handoff_return_vel = float(cfg.get("handoff_return_joint_vel", 18.0))
        handoff_return_acc = float(cfg.get("handoff_return_joint_acc", 18.0))
        return_vel = float(cfg.get("return_home_joint_vel", 12.0))
        return_acc = float(cfg.get("return_home_joint_acc", 12.0))
        handoff_auto_release = float(cfg.get("handoff_auto_release_sec", 15.0))

        def _movej(
            joints: list[float],
            label: str,
            *,
            vel: float = approach_vel,
            acc: float = approach_acc,
        ) -> None:
            motion.movej_joint(joints, label, task, vel=vel, acc=acc)

        def _advance_grasp_tcp_z() -> None:
            if grasp_tcp_z_advance_mm <= 0:
                return
            motion.move_relative_tool(
                [0.0, 0.0, grasp_tcp_z_advance_mm, 0.0, 0.0, 0.0],
                "move_charger_grasp_advance",
                task,
                vel=grasp_advance_vel,
                acc=grasp_advance_acc,
            )

        def _prepare_home() -> None:
            try:
                from cobot1.motion.dsr_imports import import_dsr_api

                import_dsr_api()["release_compliance_ctrl"]()
            except Exception:
                pass
            motion.clear_cancel()
            motion.go_home(
                task,
                label="go_home",
                lift_mm=float(cfg.get("lift_clearance_mm", 150.0)),
                cfg=cfg,
                joint_vel=home_vel,
                joint_acc=home_acc,
            )
            motion.gripper.open()

        steps = [
            ("home", _prepare_home),
            ("approach_j5", lambda: _movej(approach_j5_joint, "approach_j5")),
            ("approach_j4", lambda: _movej(approach_j4_joint, "approach_j4")),
            ("approach_prepose", lambda: _movej(prepose_joint, "approach_prepose")),
            (
                "move_charger_grasp",
                lambda: _movej(
                    grasp_joint,
                    "move_charger_grasp",
                    vel=grasp_approach_vel,
                    acc=grasp_approach_acc,
                ),
            ),
            ("move_charger_grasp_advance", _advance_grasp_tcp_z),
            (
                "grip_phone",
                lambda: grip_phone(
                    motion,
                    task,
                    "grip_phone",
                    grip_force,
                    grasp_settle,
                ),
            ),
            (
                "confirm_phone_grasp",
                lambda: confirm_phone_grasped(motion, task, "confirm_phone_grasp"),
            ),
            (
                "retract_prepose",
                lambda: _movej(prepose_joint, "retract_prepose", vel=carry_vel, acc=carry_acc),
            ),
            (
                "move_handoff",
                lambda: _movej(handoff_joint, "move_handoff", vel=carry_vel, acc=carry_acc),
            ),
            (
                "wait_handoff_release",
                lambda: wait_for_external_force(
                    motion,
                    task,
                    "wait_handoff_release",
                    cfg,
                    "핸드폰을 받아 주세요",
                    auto_release_sec=handoff_auto_release,
                ),
            ),
            ("release_phone", motion.gripper.open),
            (
                "return_prepose",
                lambda: _movej(
                    prepose_joint,
                    "return_prepose",
                    vel=handoff_return_vel,
                    acc=handoff_return_acc,
                ),
            ),
            (
                "return_j4",
                lambda: _movej(
                    approach_j4_joint,
                    "return_j4",
                    vel=handoff_return_vel,
                    acc=handoff_return_acc,
                ),
            ),
            (
                "return_j5",
                lambda: _movej(
                    approach_j5_joint,
                    "return_j5",
                    vel=handoff_return_vel,
                    acc=handoff_return_acc,
                ),
            ),
            (
                "home_finish",
                lambda: motion.go_home(
                    task,
                    label="home_finish",
                    lift_mm=float(cfg.get("lift_clearance_mm", 150.0)),
                    cfg=cfg,
                    joint_vel=return_vel,
                    joint_acc=return_acc,
                ),
            ),
        ]
        motion.run_sequence(task, steps)
