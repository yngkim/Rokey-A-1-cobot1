"""페트병 뚜껑 열기 (그리퍼 미장착 시뮬레이터: 모션으로 시뮬레이션)."""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class OpenBottleTask(BaseTask):
    name = "open_bottle"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        bottle = cfg["bottle_pose"]
        task = self.name

        motion.gripper.open()

        steps = [
            ("home", lambda: motion.go_home(task)),
            (
                "approach",
                lambda: motion.approach_pose(
                    bottle,
                    cfg["cap_approach_z_mm"],
                    "approach",
                    task,
                ),
            ),
            (
                "descend_to_cap",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -cfg["cap_approach_z_mm"] + cfg["cap_grasp_z_mm"], 0.0, 0.0, 0.0],
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
                ),
            ),
            ("release_cap", motion.gripper.open),
            (
                "retract",
                lambda: motion.retreat_z(
                    cfg["cap_approach_z_mm"],
                    "retract",
                    task,
                ),
            ),
            ("home_finish", lambda: motion.go_home(task)),
        ]
        motion.run_sequence(task, steps)
