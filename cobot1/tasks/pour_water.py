"""500ml 페트병에서 컵으로 물 따르기 — 완만한 기울이기 + 유지."""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class PourWaterTask(BaseTask):
    name = "pour_water"

    def _hold_pour(self, task: str, duration_sec: float) -> None:
        self._motion.publish_status(task, "hold_pour", "running")
        self._motion.interruptible_sleep(float(duration_sec))
        self._motion.publish_status(task, "hold_pour", "done")

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        bottle = cfg["bottle_pose"]
        cup = cfg["cup_pose"]
        task = self.name
        grasp_z = cfg["grasp_offset_z_mm"]
        pour_vel = self._scenarios["motion"].get("pour_vel")
        pour_acc = self._scenarios["motion"].get("pour_acc")

        motion.gripper.open()

        steps = [
            ("home", lambda: motion.go_home(task)),
            (
                "approach_bottle",
                lambda: motion.approach_pose(bottle, grasp_z, "approach_bottle", task),
            ),
            (
                "grasp_bottle",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -grasp_z, 0.0, 0.0, 0.0],
                    "grasp_bottle",
                    task,
                ),
            ),
            ("close_gripper", motion.gripper.close),
            ("lift_bottle", lambda: motion.retreat_z(grasp_z, "lift_bottle", task)),
            (
                "move_above_cup",
                lambda: motion.approach_pose(
                    cup,
                    cfg["pour_height_above_cup_mm"],
                    "move_above_cup",
                    task,
                ),
            ),
            (
                "pre_pour_pause",
                lambda: motion.interruptible_sleep(cfg.get("pre_pour_pause_sec", 0.5)),
            ),
            (
                "tilt_pour",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, 0.0, 0.0, cfg["pour_tilt_deg"], 0.0],
                    "tilt_pour",
                    task,
                    vel=pour_vel,
                    acc=pour_acc,
                ),
            ),
            (
                "hold_pour",
                lambda: self._hold_pour(task, cfg["pour_duration_sec"]),
            ),
            (
                "untilt",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, 0.0, 0.0, -cfg["pour_tilt_deg"], 0.0],
                    "untilt",
                    task,
                    vel=pour_vel,
                    acc=pour_acc,
                ),
            ),
        ]

        if cfg.get("return_bottle", True):
            steps.extend(
                [
                    (
                        "return_above_bottle",
                        lambda: motion.approach_pose(
                            bottle, grasp_z, "return_above_bottle", task
                        ),
                    ),
                    (
                        "lower_bottle",
                        lambda: motion.move_relative_tool(
                            [0.0, 0.0, -grasp_z, 0.0, 0.0, 0.0],
                            "lower_bottle",
                            task,
                        ),
                    ),
                    ("open_gripper", motion.gripper.open),
                    ("retract", lambda: motion.retreat_z(grasp_z, "retract", task)),
                ]
            )
        else:
            steps.append(("open_gripper", motion.gripper.open))

        steps.append(("home_finish", lambda: motion.go_home(task)))
        motion.run_sequence(task, steps)
