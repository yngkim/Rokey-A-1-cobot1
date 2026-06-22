"""임의 위치의 알약을 집어 다른 위치에 놓기."""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class PickPlacePillTask(BaseTask):
    name = "pick_place_pill"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        pick_pose = cfg["pick_pose"]
        place_pose = cfg["place_pose"]
        approach_h = self._scenarios["motion"].get("approach_height_mm", 80)
        task = self.name

        motion.gripper.open()

        steps = [
            ("home", lambda: motion.go_home(task)),
            (
                "approach_pick",
                lambda: motion.approach_pose(pick_pose, approach_h, "approach_pick", task),
            ),
            (
                "descend_pick",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -approach_h + cfg["pick_depth_mm"], 0.0, 0.0, 0.0],
                    "descend_pick",
                    task,
                ),
            ),
            ("grip_pill", motion.gripper.close),
            ("lift_pick", lambda: motion.retreat_z(approach_h, "lift_pick", task)),
            (
                "approach_place",
                lambda: motion.approach_pose(
                    place_pose,
                    approach_h,
                    "approach_place",
                    task,
                ),
            ),
            (
                "descend_place",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -approach_h + cfg["place_depth_mm"], 0.0, 0.0, 0.0],
                    "descend_place",
                    task,
                ),
            ),
            ("release_pill", motion.gripper.open),
            ("lift_place", lambda: motion.retreat_z(approach_h, "lift_place", task)),
            ("home_finish", lambda: motion.go_home(task)),
        ]
        motion.run_sequence(task, steps)
