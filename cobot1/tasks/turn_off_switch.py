"""작업공간 내 스위치 끄기 (누르기 동작 시뮬레이션)."""

from __future__ import annotations

import time

from cobot1.tasks.base import BaseTask


class TurnOffSwitchTask(BaseTask):
    name = "turn_off_switch"

    def _hold_press(self, task: str, duration_sec: float) -> None:
        self._motion.publish_status(task, "hold_press", "running")
        time.sleep(float(duration_sec))
        self._motion.publish_status(task, "hold_press", "done")

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        motion.gripper.open()

        steps = [
            ("home", lambda: motion.go_home(task)),
            (
                "approach_switch",
                lambda: motion.approach_pose(
                    cfg["switch_pose"],
                    cfg["approach_z_mm"],
                    "approach_switch",
                    task,
                ),
            ),
            (
                "contact_switch",
                lambda: motion.move_relative_tool(
                    [
                        0.0,
                        0.0,
                        -cfg["approach_z_mm"] + cfg["press_depth_mm"],
                        0.0,
                        0.0,
                        0.0,
                    ],
                    "contact_switch",
                    task,
                ),
            ),
            (
                "press_off",
                lambda: motion.move_relative_tool(
                    [0.0, cfg["press_stroke_mm"], 0.0, 0.0, 0.0, 0.0],
                    "press_off",
                    task,
                ),
            ),
            (
                "hold_press",
                lambda: self._hold_press(task, cfg["press_hold_sec"]),
            ),
            (
                "release_press",
                lambda: motion.move_relative_tool(
                    [0.0, -cfg["press_stroke_mm"], 0.0, 0.0, 0.0, 0.0],
                    "release_press",
                    task,
                ),
            ),
            (
                "retract",
                lambda: motion.retreat_z(cfg["approach_z_mm"], "retract", task),
            ),
            ("home_finish", lambda: motion.go_home(task)),
        ]
        motion.run_sequence(task, steps)
