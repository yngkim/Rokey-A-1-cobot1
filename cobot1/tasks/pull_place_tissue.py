"""휴지 뽑아서 임의 위치에 놓기."""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class PullPlaceTissueTask(BaseTask):
    name = "pull_place_tissue"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        approach_h = self._scenarios["motion"].get("approach_height_mm", 80)
        task = self.name

        motion.gripper.open()

        steps = [
            ("home", lambda: motion.go_home(task)),
            (
                "approach_tissue",
                lambda: motion.approach_pose(
                    cfg["tissue_box_pose"],
                    approach_h,
                    "approach_tissue",
                    task,
                ),
            ),
            (
                "reach_tissue",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -approach_h + cfg["pick_depth_mm"], 0.0, 0.0, 0.0],
                    "reach_tissue",
                    task,
                ),
            ),
            ("grip_tissue", motion.gripper.close),
            (
                "pull_tissue",
                lambda: motion.move_relative_tool(
                    [0.0, -cfg["pull_distance_mm"], 0.0, 0.0, 0.0, 0.0],
                    "pull_tissue",
                    task,
                ),
            ),
            ("lift_tissue", lambda: motion.retreat_z(approach_h, "lift_tissue", task)),
            (
                "approach_place",
                lambda: motion.approach_pose(
                    cfg["place_pose"],
                    approach_h,
                    "approach_place",
                    task,
                ),
            ),
            (
                "lower_place",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -approach_h + cfg["place_depth_mm"], 0.0, 0.0, 0.0],
                    "lower_place",
                    task,
                ),
            ),
            ("release_tissue", motion.gripper.open),
            ("retract_place", lambda: motion.retreat_z(approach_h, "retract_place", task)),
            ("home_finish", lambda: motion.go_home(task)),
        ]
        motion.run_sequence(task, steps)
