"""기본(홈) 위치 복귀."""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class GoHomeTask(BaseTask):
    name = "go_home"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name
        retreat = float(cfg.get("retreat_z_mm", 80))

        steps = []

        def _release_compliance() -> None:
            try:
                from cobot1.motion.dsr_imports import import_dsr_api

                import_dsr_api()["release_compliance_ctrl"]()
            except Exception:
                pass

        steps.append(("release_compliance", _release_compliance))
        if cfg.get("open_gripper", True):
            steps.append(("open_gripper", motion.gripper.open))
        if retreat > 0:
            steps.append(
                (
                    "safe_retreat",
                    lambda: motion.retreat_z(retreat, "safe_retreat", task),
                )
            )
        steps.append(("go_home", lambda: motion.go_home(task)))

        motion.run_sequence(task, steps)
