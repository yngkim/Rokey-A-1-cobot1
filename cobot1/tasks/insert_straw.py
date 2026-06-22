"""페트병 뚜껑 천공 후 빨대 삽입."""

from __future__ import annotations

import time

from cobot1.tasks.base import BaseTask


class InsertStrawTask(BaseTask):
    name = "insert_straw"

    def _pierce_cap(self, task: str, pierce_depth: float, steps: int) -> None:
        step_depth = pierce_depth / steps
        for index in range(steps):
            self._motion.move_relative_tool(
                [0.0, 0.0, -step_depth, 0.0, 0.0, 0.0],
                f"pierce_{index + 1}",
                task,
            )

    def _hold(self, task: str, step: str, duration_sec: float) -> None:
        self._motion.publish_status(task, step, "running")
        time.sleep(float(duration_sec))
        self._motion.publish_status(task, step, "done")

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        approach_h = self._scenarios["motion"].get("approach_height_mm", 80)
        approach_z = float(cfg["pierce_approach_z_mm"])
        pierce_depth = float(cfg["pierce_depth_mm"])
        insert_depth = float(cfg["insert_depth_mm"])
        task = self.name

        motion.gripper.open()

        steps = [
            ("home", lambda: motion.go_home(task)),
            (
                "approach_bottle",
                lambda: motion.approach_pose(
                    cfg["bottle_pose"],
                    approach_z,
                    "approach_bottle",
                    task,
                ),
            ),
            (
                "descend_to_cap",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -approach_z, 0.0, 0.0, 0.0],
                    "descend_to_cap",
                    task,
                ),
            ),
            (
                "pierce_cap",
                lambda: self._pierce_cap(task, pierce_depth, int(cfg["pierce_steps"])),
            ),
            (
                "retract_from_pierce",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, approach_z + pierce_depth, 0.0, 0.0, 0.0],
                    "retract_from_pierce",
                    task,
                ),
            ),
            (
                "approach_straw",
                lambda: motion.approach_pose(
                    cfg["straw_pick_pose"],
                    approach_h,
                    "approach_straw",
                    task,
                ),
            ),
            (
                "grasp_straw",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -approach_h + cfg["straw_grasp_depth_mm"], 0.0, 0.0, 0.0],
                    "grasp_straw",
                    task,
                ),
            ),
            ("close_gripper", motion.gripper.close),
            ("lift_straw", lambda: motion.retreat_z(approach_h, "lift_straw", task)),
            (
                "move_to_bottle",
                lambda: motion.approach_pose(
                    cfg["bottle_pose"],
                    approach_z,
                    "move_to_bottle",
                    task,
                ),
            ),
            (
                "insert_straw",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, -(approach_z + insert_depth), 0.0, 0.0, 0.0],
                    "insert_straw",
                    task,
                ),
            ),
            (
                "hold_insert",
                lambda: self._hold(task, "hold_insert", cfg["insert_hold_sec"]),
            ),
            ("release_straw", motion.gripper.open),
            (
                "retract_finish",
                lambda: motion.move_relative_tool(
                    [0.0, 0.0, approach_z + insert_depth, 0.0, 0.0, 0.0],
                    "retract_finish",
                    task,
                ),
            ),
            ("home_finish", lambda: motion.go_home(task)),
        ]
        motion.run_sequence(task, steps)
