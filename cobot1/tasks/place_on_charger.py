"""사용자에게서 스마트폰을 받아 무선충전기에 놓기 (pick_from_charger 역순)."""

from __future__ import annotations

from cobot1.motion.nudge_handoff import (
    confirm_phone_grasped,
    grip_phone,
    wait_for_external_force,
)
from cobot1.tasks.base import BaseTask


class PlaceOnChargerTask(BaseTask):
    name = "place_on_charger"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        motion.set_recovery_joint(home_joint)

        approach_j5_joint = list(cfg["charger_approach_j5_joint"])
        approach_j4_joint = list(cfg["charger_approach_j4_joint"])
        prepose_joint = list(cfg["charger_approach_prepose_joint"])
        charger_front_joint = list(
            cfg.get(
                "charger_front_joint",
                [-2.8, 29.27, 87.8, 111.76, -38.5, 0.66],
            )
        )
        charger_place_joint = list(
            cfg.get(
                "charger_place_joint",
                [-4.39, 34.79, 95.87, 77.0, -34.75, 35.33],
            )
        )
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
        handoff_return_vel = float(cfg.get("handoff_return_joint_vel", 18.0))
        handoff_return_acc = float(cfg.get("handoff_return_joint_acc", 18.0))
        place_return_vel = float(
            cfg.get("charger_place_return_joint_vel", handoff_return_vel)
        )
        place_return_acc = float(
            cfg.get("charger_place_return_joint_acc", handoff_return_acc)
        )
        return_vel = float(cfg.get("charger_place_home_joint_vel", cfg.get("return_home_joint_vel", 12.0)))
        return_acc = float(cfg.get("charger_place_home_joint_acc", cfg.get("return_home_joint_acc", 12.0)))

        def _movej(
            joints: list[float],
            label: str,
            *,
            vel: float = approach_vel,
            acc: float = approach_acc,
        ) -> None:
            motion.movej_joint(joints, label, task, vel=vel, acc=acc)

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
            # pick과 동일 J5 포즈만 거친 뒤 사용자 인계 위치로 직행
            ("approach_j5", lambda: _movej(approach_j5_joint, "approach_j5")),
            (
                "move_handoff",
                lambda: _movej(handoff_joint, "move_handoff", vel=carry_vel, acc=carry_acc),
            ),
            (
                "wait_handoff_grasp",
                lambda: wait_for_external_force(
                    motion,
                    task,
                    "wait_handoff_grasp",
                    cfg,
                    "핸드폰을 올려 주세요",
                    timeout_sec=float(cfg.get("handoff_grasp_timeout_sec", 0)),
                ),
            ),
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
            # pick 거치대 접근(j4→prepose→거치대)과 동일 순서
            ("approach_j4", lambda: _movej(approach_j4_joint, "approach_j4", vel=carry_vel, acc=carry_acc)),
            (
                "approach_prepose",
                lambda: _movej(prepose_joint, "approach_prepose", vel=carry_vel, acc=carry_acc),
            ),
            (
                "move_charger_front",
                lambda: _movej(
                    charger_front_joint,
                    "move_charger_front",
                    vel=grasp_approach_vel,
                    acc=grasp_approach_acc,
                ),
            ),
            (
                "move_charger_place",
                lambda: _movej(
                    charger_place_joint,
                    "move_charger_place",
                    vel=grasp_approach_vel,
                    acc=grasp_approach_acc,
                ),
            ),
            ("release_phone", motion.gripper.open),
            # pick 접근(j5→j4→prepose→거치대) 역순으로 홈 복귀
            (
                "return_prepose",
                lambda: _movej(
                    prepose_joint,
                    "return_prepose",
                    vel=place_return_vel,
                    acc=place_return_acc,
                ),
            ),
            (
                "return_j4",
                lambda: _movej(
                    approach_j4_joint,
                    "return_j4",
                    vel=place_return_vel,
                    acc=place_return_acc,
                ),
            ),
            (
                "return_j5",
                lambda: _movej(
                    approach_j5_joint,
                    "return_j5",
                    vel=place_return_vel,
                    acc=place_return_acc,
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
