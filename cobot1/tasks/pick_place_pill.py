"""알약 서랍에서 꺼내 지정 위치로 옮기기."""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class PickPlacePillTask(BaseTask):
    name = "pick_place_pill"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        drawer = cfg["drawer_pose"]
        place_pose = cfg["place_pose"]
        approach_z = cfg["drawer_approach_z_mm"]
        pick_depth = cfg["pick_depth_mm"]
        task = self.name

        motion.gripper.open()

        steps = [
            ("home", lambda: motion.go_home(task)),
            (
                "approach_drawer",
                lambda: motion.approach_pose(
                    drawer, approach_z, "approach_drawer", task
                ),
            ),
            (
                "reach_into_drawer",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -(approach_z - pick_depth), 0.0, 0.0, 0.0],
                    "reach_into_drawer",
                    task,
                ),
            ),
            ("grip_pill", motion.gripper.close),
            (
                "pull_out_drawer",
                lambda: motion.retreat_z(
                    approach_z + cfg.get("drawer_pull_back_mm", 10),
                    "pull_out_drawer",
                    task,
                ),
            ),
            (
                "approach_place",
                lambda: motion.approach_pose(
                    place_pose, approach_z, "approach_place", task
                ),
            ),
            (
                "descend_place",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -(approach_z - cfg["place_depth_mm"]), 0.0, 0.0, 0.0],
                    "descend_place",
                    task,
                ),
            ),
            ("release_pill", motion.gripper.open),
            ("lift_place", lambda: motion.retreat_z(approach_z, "lift_place", task)),
            ("home_finish", lambda: motion.go_home(task)),
        ]
        motion.run_sequence(task, steps)
