"""알약 서랍에서 꺼내 약통에 덤프 후 서랍장 위에 올려두기.

전제:
  로봇은 home, 그리퍼 열림. 서랍 안에 약 봉지가 있음.

흐름:
  home → 서랍 손잡이 접근·파지 → 서랍 당김
  → Z 유지·XY·Z(약통 위) → J6 -180° 덤프 → 대기 → 원자세 복귀
  → Z↑·XY(서랍장 상공) → Z 수직 하강(느림, 내려놓기) → 그리퍼 열기 → 후퇴 → home
"""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


def _normalize_joint_angle(deg: float) -> float:
    while deg > 180.0:
        deg -= 360.0
    while deg < -180.0:
        deg += 360.0
    return deg


def _joint_with_j6_delta(base: list[float], delta_deg: float) -> list[float]:
    target = list(base)
    target[5] = _normalize_joint_angle(target[5] + delta_deg)
    return target


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
        cabinet_top_joint = list(cfg.get(
            "cabinet_top_joint",
            [-7.98, 29.54, 106.28, -3.74, -46.16, 2.36],
        ))
        cabinet_place_joint = list(cfg.get(
            "cabinet_place_joint",
            [-8.0, 32.31, 106.91, -3.74, -49.44, 2.27],
        ))
        cabinet_retract_joint = list(cfg.get(
            "cabinet_retract_joint",
            [-8.35, 26.43, 117.68, -3.85, -54.17, 2.20],
        ))

        dump_tilt_delta = float(cfg.get("dump_tilt_delta_j6_deg", -180.0))
        dump_duration = float(cfg.get("dump_duration_sec", 2.0))
        dump_jvel = float(cfg.get("dump_joint_vel", 8.0))
        dump_jacc = float(cfg.get("dump_joint_acc", 8.0))

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
        place_vel = list(cfg.get("place_vel", [5, 3]))
        place_acc = list(cfg.get("place_acc", [10, 6]))
        retract_jvel = float(cfg.get("retract_joint_vel", 8.0))
        retract_jacc = float(cfg.get("retract_joint_acc", 8.0))

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

        def _move_j6_delta(
            delta_deg: float,
            label: str,
            vel: float,
            acc: float,
        ) -> None:
            target = _joint_with_j6_delta(pill_above_joint, delta_deg)
            motion.movej_joint(target, label, task, vel=vel, acc=acc)

        def _move_to_drawer_grasp() -> None:
            _approach_joint(drawer_grasp_joint, "move_drawer_grasp")

        def _pause_safety_for_drawer() -> None:
            """손잡이 파지·이송·내려놓기 중 접촉력은 정상 — 외력 감시 일시 해제."""
            motion.pause_safety_force_abort()

        def _resume_safety_after_drawer() -> None:
            motion.resume_safety_force_abort()

        def _grasp_drawer() -> None:
            motion.publish_status(
                task, "grasp_drawer", "running",
                f"서랍 손잡이 파지 중 (닫힘 대기 {drawer_grasp_settle:.1f}초)",
            )
            motion.gripper.grip_and_verify(
                "pill_drawer",
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

        def _dump_tilt() -> None:
            _move_j6_delta(dump_tilt_delta, "dump_tilt", dump_jvel, dump_jacc)

        def _hold_dump() -> None:
            motion.publish_status(
                task, "hold_dump", "running",
                f"{dump_duration:.1f}초간 약 봉지 덤프 대기",
            )
            motion.interruptible_sleep(dump_duration)
            motion.publish_status(task, "hold_dump", "done")

        def _dump_untilt() -> None:
            _move_j6_delta(0.0, "dump_untilt", dump_jvel, dump_jacc)

        def _move_cabinet_top() -> None:
            """Z↑ → XY 수평 이동만 (상공 유지, 하강은 lower_to_cabinet에서 수직·느리게)."""
            top_tcp = _fkin_tcp(cabinet_top_joint)
            place_tcp = _fkin_tcp(cabinet_place_joint)
            cur = motion.get_current_tcp_pose()
            travel_z = max(cur[2], top_tcp[2], place_tcp[2]) + lift
            motion.move_vertical_to_z(
                travel_z, cur, "cabinet_lift", task,
                vel=carry_vel, acc=carry_acc,
            )
            motion.move_task_pose(
                [top_tcp[0], top_tcp[1], travel_z,
                 top_tcp[3], top_tcp[4], top_tcp[5]],
                "cabinet_travel", task,
                vel=carry_vel, acc=carry_acc,
            )

        def _lower_to_cabinet() -> None:
            """상공에서 Z만 수직 하강 → 내려놓기 자세 (movej 보간 과하강 방지)."""
            place_tcp = _fkin_tcp(cabinet_place_joint)
            cur = motion.get_current_tcp_pose()
            motion.move_vertical_to_z(
                place_tcp[2], cur, "lower_to_cabinet_z", task,
                vel=place_vel, acc=place_acc,
            )
            motion.move_task_pose(
                place_tcp, "lower_to_cabinet_pose", task,
                vel=place_vel, acc=place_acc,
            )

        def _release_drawer() -> None:
            motion.gripper.open()

        def _retract_from_cabinet() -> None:
            """내려놓은 뒤 살짝 뒤로·위로 후퇴 (홈 가기 전)."""
            motion.movej_joint(
                cabinet_retract_joint, "retract_from_cabinet", task,
                vel=retract_jvel, acc=retract_jacc,
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
            ("prepare_home",         _prepare_home),
            ("move_drawer_grasp",    _move_to_drawer_grasp),
            ("pause_safety_drawer",  _pause_safety_for_drawer),
            ("grasp_drawer",         _grasp_drawer),
            ("pull_drawer",          _pull_drawer),
            ("move_above_bottle",    _move_above_bottle),
            ("dump_tilt",            _dump_tilt),
            ("hold_dump",            _hold_dump),
            ("dump_untilt",          _dump_untilt),
            ("move_cabinet_top",     _move_cabinet_top),
            ("lower_to_cabinet",     _lower_to_cabinet),
            ("release_drawer",       _release_drawer),
            ("resume_safety_drawer", _resume_safety_after_drawer),
            ("retract_from_cabinet", _retract_from_cabinet),
            ("retract_and_home",     _retract_and_home),
        ]
        motion.run_sequence(task, steps)
