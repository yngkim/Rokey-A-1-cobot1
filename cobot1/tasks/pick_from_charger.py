"""스마트폰을 무선충전기에서 가져오기."""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class PickFromChargerTask(BaseTask):
    name = "pick_from_charger"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        phone = cfg["phone_pose"]
        charger = cfg["charger_pose"]
        approach_z = cfg["approach_z_mm"]
        task = self.name

        motion.gripper.open()

        steps = [
            ("home", lambda: motion.go_home(task)),
            (
                "approach_charger",
                lambda: motion.approach_pose(
                    charger, approach_z, "approach_charger", task
                ),
            ),
            (
                "grasp_phone",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -(approach_z - cfg["grasp_depth_mm"]), 0.0, 0.0, 0.0],
                    "grasp_phone",
                    task,
                ),
            ),
            ("grip_phone", motion.gripper.close),
            ("lift_phone", lambda: motion.retreat_z(approach_z, "lift_phone", task)),
            (
                "approach_bedside",
                lambda: motion.approach_pose(
                    phone, approach_z, "approach_bedside", task
                ),
            ),
            (
                "place_phone",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -(approach_z - cfg["place_depth_mm"]), 0.0, 0.0, 0.0],
                    "place_phone",
                    task,
                ),
            ),
            ("release_phone", motion.gripper.open),
            ("retract", lambda: motion.retreat_z(approach_z, "retract", task)),
            ("home_finish", lambda: motion.go_home(task)),
        ]
        motion.run_sequence(task, steps)
