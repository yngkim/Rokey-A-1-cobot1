"""알약 서랍에서 꺼내 약통에 놓기 (조인트 티칭 기반).

전제:
  로봇은 home, 그리퍼 열림.

흐름:
  home → 서랍 손잡이 접근·파지 → 서랍 당기기
  → Z 유지·XY 수평·Z 조정(약통 위) → 약통 아래 movej
  → 그리퍼 열기 → 후퇴 → home

추후 확장:
  pull_drawer 와 move_above_bottle 사이에 알약 집기 단계 삽입 예정.
"""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class PickPlacePillTask(BaseTask):
    name = "pick_place_pill"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        motion.set_recovery_joint(home_joint)

        from cobot1.motion.dsr_imports import import_dsr_api

        lift = float(cfg.get("lift_clearance_mm", 120.0))

        drawer_grasp_joint = list(cfg.get(
            "drawer_grasp_joint",
            [-8.1, 40.74, 108.1, -3.4, -58.88, 1.65],
        ))
        drawer_pulled_joint = list(cfg.get(
            "drawer_pulled_joint",
            [-9.71, 30.83, 133.33, -4.39, -74.03, 1.19],
        ))
        pill_above_joint = list(cfg.get(
            "pill_above_joint",
            [18.86, 14.23, 104.58, -117.22, -49.04, 83.46],
        ))
        pill_below_joint = list(cfg.get(
            "pill_below_joint",
            [21.03, 21.02, 106.5, -119.41, -43.71, 83.46],
        ))
        pill_retract_joint = list(cfg.get(
            "pill_retract_joint",
            [4.58, 5.53, 104.67, -131.2, -65.3, 90.08],
        ))

        grasp_vel = list(cfg.get("grasp_vel", [15, 10]))
        grasp_acc = list(cfg.get("grasp_acc", [30, 15]))
        fast_vel = list(cfg.get("fast_vel", [80, 60]))
        fast_acc = list(cfg.get("fast_acc", [200, 150]))
        fast_jvel = float(cfg.get("fast_joint_vel", 60.0))
        fast_jacc = float(cfg.get("fast_joint_acc", 60.0))
        carry_jvel = float(cfg.get("carry_joint_vel", cfg.get("pull_joint_vel", 15.0)))
        carry_jacc = float(cfg.get("carry_joint_acc", cfg.get("pull_joint_acc", 15.0)))
        carry_vel = list(cfg.get("carry_vel", cfg.get("return_vel", [25, 20])))
        carry_acc = list(cfg.get("carry_acc", cfg.get("return_acc", [50, 40])))
        return_jvel = float(cfg.get("return_joint_vel", 15.0))
        return_jacc = float(cfg.get("return_joint_acc", 15.0))
        return_vel = list(cfg.get("return_vel", [25, 20]))
        return_acc = list(cfg.get("return_acc", [50, 40]))

        drawer_grip_force = float(cfg.get("drawer_grip_force", 100.0))
        drawer_grasp_settle = float(cfg.get("drawer_grasp_settle_sec", 4.5))

        def _fkin_tcp(joints: list[float]) -> list[float]:
            return [float(v) for v in import_dsr_api()["fkin"](joints)]

        def _release_compliance() -> None:
            try:
                import_dsr_api()["release_compliance_ctrl"]()
            except Exception:
                pass

        def _prepare_home() -> None:
            _release_compliance()
            motion.clear_cancel()
            motion.movej_joint(home_joint, "move_home", task,
                               vel=fast_jvel, acc=fast_jacc)
            motion.gripper.open()

        def _approach_joint(joints: list[float], label: str) -> None:
            """빈 그리퍼로 목표 조인트에 TCP Z↑→XY→Z↓ 접근."""
            tcp = _fkin_tcp(joints)
            cur = motion.get_current_tcp_pose()
            travel_z = max(cur[2], tcp[2]) + lift
            motion.move_vertical_to_z(
                travel_z, cur, f"{label}_lift", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.move_task_pose(
                [tcp[0], tcp[1], travel_z, tcp[3], tcp[4], tcp[5]],
                f"{label}_travel", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.move_task_pose(
                tcp, f"{label}_descend", task,
                vel=grasp_vel, acc=grasp_acc,
            )

        def _move_joint_via_xy_z(joints: list[float], label: str) -> None:
            """현재 Z 유지 → XY 수평 → 목표 Z·자세 (fkin TCP)."""
            tgt = _fkin_tcp(joints)
            cur = motion.get_current_tcp_pose()
            motion.move_task_pose(
                [tgt[0], tgt[1], cur[2], cur[3], cur[4], cur[5]],
                f"{label}_travel", task,
                vel=carry_vel, acc=carry_acc,
            )
            motion.move_task_pose(
                tgt, f"{label}_descend", task,
                vel=grasp_vel, acc=grasp_acc,
            )

        def _move_to_drawer_grasp() -> None:
            _approach_joint(drawer_grasp_joint, "move_drawer_grasp")

        def _grasp_drawer() -> None:
            motion.publish_status(
                task, "grasp_drawer", "running",
                f"서랍 손잡이 파지 중 (닫힘 대기 {drawer_grasp_settle:.1f}초)",
            )
            motion.gripper.grip(
                force=drawer_grip_force,
                width_units=0,
                wait_sec=drawer_grasp_settle,
            )
            motion.publish_status(
                task, "grasp_drawer", "done",
                f"그리퍼 닫힘 대기 완료 ({drawer_grasp_settle:.1f}초)",
            )

        def _pull_drawer() -> None:
            motion.movej_joint(
                drawer_pulled_joint, "pull_drawer", task,
                vel=carry_jvel, acc=carry_jacc,
            )

        def _move_above_bottle() -> None:
            _move_joint_via_xy_z(pill_above_joint, "move_above_bottle")

        def _move_below_bottle() -> None:
            motion.movej_joint(
                pill_below_joint, "move_below_bottle", task,
                vel=carry_jvel, acc=carry_jacc,
            )

        def _retract_after_place() -> None:
            motion.movej_joint(
                pill_retract_joint, "retract_after_place", task,
                vel=return_jvel, acc=return_jacc,
            )

        def _retract_and_home() -> None:
            """Z↑ → home XY 상공 → home 조인트."""
            cur = motion.get_current_tcp_pose()
            home_tcp = _fkin_tcp(home_joint)
            travel_z = max(cur[2], home_tcp[2]) + lift
            motion.move_vertical_to_z(
                travel_z, cur, "home_lift", task,
                vel=return_vel, acc=return_acc,
            )
            motion.move_task_pose(
                [home_tcp[0], home_tcp[1], travel_z,
                 home_tcp[3], home_tcp[4], home_tcp[5]],
                "home_travel", task,
                vel=return_vel, acc=return_acc,
            )
            motion.movej_joint(home_joint, "home_finish", task,
                               vel=return_jvel, acc=return_jacc)

        steps = [
            ("prepare_home",        _prepare_home),
            ("move_drawer_grasp",   _move_to_drawer_grasp),
            ("grasp_drawer",        _grasp_drawer),
            ("pull_drawer",         _pull_drawer),
            # 추후: ("open_for_pill", ...), ("move_pill_grasp", ...), ("grasp_pill", ...)
            ("move_above_bottle",   _move_above_bottle),
            ("move_below_bottle",   _move_below_bottle),
            ("release_pill",        motion.gripper.open),
            ("retract_after_place", _retract_after_place),
            ("retract_and_home",    _retract_and_home),
        ]
        motion.run_sequence(task, steps)
