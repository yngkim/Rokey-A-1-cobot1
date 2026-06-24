"""500ml 페트병에서 컵으로 물 따르기.

흐름:
  홈 이동 → 그리퍼 열기 → 병 위 접근
  → 순응 하강 파지(Z 유연) → 들어올리기
  → 컵 위로 이동 → 기울이기 → 붓기(유지) → 원상복귀
  → (옵션) 병 되돌려 놓기 → 홈 복귀
"""

from __future__ import annotations

from cobot1.motion.compliance import compliance_session
from cobot1.tasks.base import BaseTask


class PourWaterTask(BaseTask):
    name = "pour_water"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name
        logger = motion._node.get_logger()

        bottle = list(cfg["bottle_pose"])
        cup = list(cfg["cup_pose"])
        grasp_z = float(cfg["grasp_offset_z_mm"])
        pour_height = float(cfg["pour_height_above_cup_mm"])
        pour_tilt = float(cfg["pour_tilt_deg"])
        pour_duration = float(cfg["pour_duration_sec"])
        pre_pause = float(cfg.get("pre_pour_pause_sec", 0.5))
        pour_vel = self._scenarios["motion"].get("pour_vel", [40, 20])
        pour_acc = self._scenarios["motion"].get("pour_acc", [80, 40])

        # Z 순응 설정: 병 위치 오차나 바닥 접촉 시 과도한 힘 방지 (600 N/m)
        _GRASP_COMPLIANCE = [3000, 3000, 600, 200, 200, 200]

        def _go_home() -> None:
            motion.go_home(task)

        def _open_and_approach_bottle() -> None:
            """그리퍼 열기 + 페트병 위 접근 위치로 이동.

            gripper.open()을 run_sequence 안에서 호출해 안전 모니터링을 유지한다.
            approach_pose는 bottle_pose에서 grasp_z(mm)만큼 BASE Z+ 방향으로 오프셋.
            """
            motion.gripper.open()
            motion.approach_pose(bottle, grasp_z, "approach_bottle", task)

        def _grasp_bottle() -> None:
            """순응 제어 하에서 하강 후 페트병 파지.

            stx Z=600 N/m: 병 위치 오차나 표면 닿음 시 힘 자동 제한.
            """
            with compliance_session(_GRASP_COMPLIANCE, time_sec=0.3, node_logger=logger):
                motion.move_relative_tool(
                    [0.0, 0.0, -grasp_z, 0.0, 0.0, 0.0],
                    "grasp_descent",
                    task,
                )
            motion.gripper.close()

        def _lift_bottle() -> None:
            """병을 들어올려 이동 안전 높이 확보."""
            motion.retreat_z(grasp_z, "lift_bottle", task)

        def _move_above_cup() -> None:
            """컵 위 따르기 위치로 이동 (pour_height_above_cup_mm 높이)."""
            motion.approach_pose(cup, pour_height, "move_above_cup", task)

        def _tilt_pour() -> None:
            """툴 Y축 기준으로 완만하게 기울여 물 따르기."""
            motion.move_relative_tool(
                [0.0, 0.0, 0.0, 0.0, pour_tilt, 0.0],
                "tilt_pour",
                task,
                vel=pour_vel,
                acc=pour_acc,
            )

        def _hold_pour() -> None:
            motion.publish_status(task, "hold_pour", "running", f"{pour_duration:.1f}초간 따르기")
            motion.interruptible_sleep(pour_duration)
            motion.publish_status(task, "hold_pour", "done")

        def _untilt() -> None:
            """기울인 각도를 원상복귀."""
            motion.move_relative_tool(
                [0.0, 0.0, 0.0, 0.0, -pour_tilt, 0.0],
                "untilt",
                task,
                vel=pour_vel,
                acc=pour_acc,
            )

        steps: list = [
            ("go_home",                _go_home),
            ("open_approach_bottle",   _open_and_approach_bottle),
            ("grasp_bottle",           _grasp_bottle),
            ("lift_bottle",            _lift_bottle),
            ("move_above_cup",         _move_above_cup),
            ("pre_pour_pause",         lambda: motion.interruptible_sleep(pre_pause)),
            ("tilt_pour",              _tilt_pour),
            ("hold_pour",              _hold_pour),
            ("untilt",                 _untilt),
        ]

        if cfg.get("return_bottle", True):
            def _return_above_bottle() -> None:
                motion.approach_pose(bottle, grasp_z, "return_above_bottle", task)

            def _lower_and_release() -> None:
                """순응 제어 하에서 병을 원위치에 내려놓고 그리퍼 열기."""
                with compliance_session(_GRASP_COMPLIANCE, time_sec=0.3, node_logger=logger):
                    motion.move_relative_tool(
                        [0.0, 0.0, -grasp_z, 0.0, 0.0, 0.0],
                        "lower_bottle",
                        task,
                    )
                motion.gripper.open()

            def _retract() -> None:
                motion.retreat_z(grasp_z, "retract", task)

            steps += [
                ("return_above_bottle", _return_above_bottle),
                ("lower_and_release",   _lower_and_release),
                ("retract",             _retract),
            ]
        else:
            steps.append(("open_gripper", motion.gripper.open))

        steps.append(("home_finish", lambda: motion.go_home(task)))
        motion.run_sequence(task, steps)
