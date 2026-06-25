"""기본(홈) 위치 복귀."""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class GoHomeTask(BaseTask):
    name = "go_home"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        steps = []

        def _release_compliance() -> None:
            try:
                from cobot1.motion.dsr_imports import import_dsr_api

                import_dsr_api()["release_compliance_ctrl"]()
            except Exception:
                pass

        def _return_home() -> None:
            lift_mm = float(cfg.get("lift_clearance_mm", 150.0))
            motion.go_home(task, lift_mm=lift_mm, cfg=cfg)

        steps.append(("release_compliance", _release_compliance))
        if cfg.get("open_gripper", True):
            steps.append(("open_gripper", motion.gripper.open))
        steps.append(("go_home", _return_home))

        motion.run_sequence(task, steps)
