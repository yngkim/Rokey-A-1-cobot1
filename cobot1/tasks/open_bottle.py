"""페트병 뚜껑 열기 — 단계별 비틀기 + 뚜껑 들어올리기."""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class OpenBottleTask(BaseTask):
    name = "open_bottle"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        bottle = cfg["bottle_pose"]
        task = self.name
        approach_z = cfg["cap_approach_z_mm"]
        grasp_z = cfg["cap_grasp_z_mm"]

        motion.gripper.open()

        steps = [
            ("home", lambda: motion.go_home(task)),
            (
                "approach",
                lambda: motion.approach_pose(bottle, approach_z, "approach", task),
            ),
            (
                "descend_to_cap",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -(approach_z - grasp_z), 0.0, 0.0, 0.0],
                    "descend_to_cap",
                    task,
                ),
            ),
            ("grip_cap", motion.gripper.close),
            (
                "press_down",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -cfg["twist_down_mm"], 0.0, 0.0, 0.0],
                    "press_down",
                    task,
                ),
            ),
            (
                "twist_open",
                lambda: motion.rotate_tool_z_steps(
                    cfg["twist_angle_deg"],
                    int(cfg["twist_steps"]),
                    "twist",
                    task,
                    pause_sec=0.2,
                ),
            ),
            (
                "lift_cap",
                lambda: motion.retreat_z(cfg["cap_lift_mm"], "lift_cap", task),
            ),
            ("release_cap", motion.gripper.open),
            ("retract", lambda: motion.retreat_z(approach_z, "retract", task)),
            ("home_finish", lambda: motion.go_home(task)),
        ]
        motion.run_sequence(task, steps)
