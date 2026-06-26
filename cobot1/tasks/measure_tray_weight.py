"""식판 파지 상태에서 tool force Z축으로 식전/식후 무게를 측정."""

from __future__ import annotations

from cobot1.motion.tray_weigh import (
    capture_tray_weight,
    record_tray_weight_reading,
    resolve_tray_phase,
)
from cobot1.runtime_state import get_tray_weight_session
from cobot1.tasks.base import BaseTask


class MeasureTrayWeightTask(BaseTask):
    name = "measure_tray_weight"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        motion.set_recovery_joint(home_joint)

        if cfg.get("go_home_first", False):
            motion.go_home(
                task,
                label="go_home",
                lift_mm=float(cfg.get("lift_clearance_mm", 150.0)),
            )

        if not motion.gripper.is_closed:
            motion.publish_status(
                task,
                "warn_gripper_open",
                "running",
                "그리퍼가 열린 상태입니다. 식판을 잡은 뒤 측정하는 것을 권장합니다.",
            )

        phase = resolve_tray_phase(cfg)
        care_user_id = str(cfg.get("care_user_id", "patient_01"))

        reading = capture_tray_weight(motion, cfg, phase=phase, task=task)
        intake_pct = record_tray_weight_reading(
            reading,
            cfg,
            task=task,
            care_user_id=care_user_id,
        )

        if intake_pct is not None:
            session = get_tray_weight_session()
            motion.publish_status(
                task,
                "meal_intake",
                "done",
                f"식사량 약 {int(round(intake_pct))}% 섭취",
                extra={
                    "intake_pct": round(intake_pct, 1),
                    "remaining_pct": round(100.0 - intake_pct, 1),
                    "before_fz": session.get("before_fz") if session else None,
                    "after_fz": reading.fz_n,
                },
            )
