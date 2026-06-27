"""빈 트레이+식판 공차 Fz 측정·저장 (CLI 전용, UI 미노출)."""

from __future__ import annotations

from cobot1.motion.tray_weigh import capture_tray_weight
from cobot1.motion.user_handoff import release_tray_at_station
from cobot1.runtime_state import save_tray_tare
from cobot1.tasks.base import BaseTask


class CalibrateTrayTareTask(BaseTask):
    name = "calibrate_tray_tare"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name
        weigh_cfg = dict(self._scenarios.get("measure_tray_weight", {}))

        home_joint = list(self._scenarios["motion"]["home_joint"])
        motion.set_recovery_joint(home_joint)

        from cobot1.motion.dsr_imports import import_dsr_api

        dsr = import_dsr_api()

        tray_grasp_joint = list(cfg["tray_grasp_joint"])
        grip_force = float(cfg.get("tray_grip_force", 120.0))
        grip_settle = float(cfg.get("grip_settle_sec", 3.0))
        home_vel = float(cfg.get("home_joint_vel", 12.0))
        home_acc = float(cfg.get("home_joint_acc", 12.0))
        grasp_vel = float(cfg.get("grasp_joint_vel", 8.0))
        grasp_acc = float(cfg.get("grasp_joint_acc", 8.0))
        carry_vel = list(cfg.get("carry_vel", [20, 15]))
        carry_acc = list(cfg.get("carry_acc", [40, 30]))
        descend_vel = list(cfg.get("descend_vel", [12, 8]))
        descend_acc = list(cfg.get("descend_acc", [24, 16]))
        lift = float(cfg.get("lift_clearance_mm", 150.0))
        return_vel = float(cfg.get("return_home_joint_vel", home_vel))
        return_acc = float(cfg.get("return_home_joint_acc", home_acc))

        def _release_compliance() -> None:
            try:
                dsr["release_compliance_ctrl"]()
            except Exception:
                pass

        def _prepare() -> None:
            _release_compliance()
            motion.clear_cancel()
            motion.go_home(
                task,
                label="home",
                lift_mm=lift,
                joint_vel=home_vel,
                joint_acc=home_acc,
                cfg={
                    "lift_clearance_mm": lift,
                    "carry_vel": carry_vel,
                    "carry_acc": carry_acc,
                    "descend_vel": descend_vel,
                    "descend_acc": descend_acc,
                },
            )
            motion.gripper.open()

        def _move_to_tray_grasp() -> None:
            motion.movej_joint(
                tray_grasp_joint,
                "move_tray_grasp",
                task,
                vel=grasp_vel,
                acc=grasp_acc,
            )

        def _grasp_tray() -> None:
            motion.publish_status(
                task,
                "grasp_tray",
                "running",
                f"빈 트레이 파지 중 (닫힘 대기 {grip_settle:.1f}초)",
            )
            motion.gripper.grip(
                force=grip_force,
                width_units=0,
                wait_sec=grip_settle,
            )
            if not motion.gripper.is_closed:
                from cobot1.motion.exceptions import CobotError

                raise CobotError(
                    "트레이를 잡지 못했습니다.",
                    code="GRIPPER_NOT_CLOSED",
                    user_message="빈 트레이·식판 위치를 확인해 주세요.",
                )
            motion.publish_status(task, "grasp_tray", "done", "트레이 파지 완료")

        def _measure_tare() -> None:
            reading = capture_tray_weight(
                motion,
                weigh_cfg,
                phase="tare",
                task=task,
                at_current_pose=True,
                carry_cfg=cfg,
                lift_before_measure=True,
                lower_after_measure=True,
            )
            save_tray_tare(reading.fz_n, source=task)
            motion._ctx.node.get_logger().info(
                f"[{task}] 공차 저장: Fz={reading.fz_n:.2f} N "
                f"(|Fz|={abs(reading.fz_n):.2f} N) → ~/.cobot1/tray_tare.json"
            )
            motion.publish_status(
                task,
                "tare_saved",
                "done",
                f"공차 저장 |Fz|={abs(reading.fz_n):.1f} N",
                extra={"tare_fz": round(reading.fz_n, 3)},
            )

        def _release_tray() -> None:
            release_tray_at_station(motion, task)

        def _go_home() -> None:
            motion.go_home(
                task,
                label="home_finish",
                lift_mm=lift,
                joint_vel=return_vel,
                joint_acc=return_acc,
                cfg={
                    "lift_clearance_mm": lift,
                    "carry_vel": carry_vel,
                    "carry_acc": carry_acc,
                    "descend_vel": descend_vel,
                    "descend_acc": descend_acc,
                },
            )

        steps = [
            ("prepare", _prepare),
            ("move_tray_grasp", _move_to_tray_grasp),
            ("grasp_tray", _grasp_tray),
            ("measure_tare", _measure_tare),
            ("release_tray", _release_tray),
            ("go_home", _go_home),
        ]
        motion.run_sequence(task, steps)
