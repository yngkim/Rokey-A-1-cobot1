"""컵에 물 따르기 (몸통 파지 + J6 구간별 기울여 붓기).

전제:
  open_bottle 직후 — 로봇은 home, 그리퍼 열림, 물병은 컵홀더에 개봉된 채 꽂혀 있음.

흐름:
  몸통 TCP 접근 → 티칭 조인트 정렬(body_grasp_joint) → 파지
  → 컵 옆 이동 → cup_side_joint 정렬
  → J6 빠름(세운→중간) → 느림(중간→cup_pour_tilt_joint) 기울임 → 유지
  → J6 빠름/느림 세움 → 컵홀더 복귀 → 그리퍼 열기 → 홈 → J6 복원
  (close_bottle 시작 전 상태)

조인트 각도는 scenarios.yaml 티칭값을 movej로 그대로 맞춘다.
TCP movel만 쓰면 J6 IK 분기로 -63° 티칭과 다른 각(±120° 등)이 선택될 수 있다.
"""

from __future__ import annotations

import math

from cobot1.motion.pose_utils import offset_joint_tcp_translation
from cobot1.tasks.base import BaseTask


def _normalize_joint_angle(deg: float) -> float:
    while deg > 180.0:
        deg -= 360.0
    while deg < -180.0:
        deg += 360.0
    return deg


class PourWaterTask(BaseTask):
    name = "pour_water"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        motion.set_recovery_joint(home_joint)

        from cobot1.motion.dsr_imports import import_dsr_api

        dsr = import_dsr_api()
        wp = self._scenarios["water_poses"]
        lift = float(wp.get("lift_clearance_mm", 120.0))
        bottle_dz = float(wp.get("bottle_height_offset_mm", 0.0))
        body_grasp_z_offset = float(cfg.get("body_grasp_z_offset_mm", 0.0))
        body_grasp_y_offset = float(cfg.get("body_grasp_y_offset_mm", 0.0))

        body_grasp_joint = offset_joint_tcp_translation(
            cfg.get(
                "body_grasp_joint",
                [-41.99, 44.05, 101.32, 52.69, 112.6, -63.1],
            ),
            dy_mm=body_grasp_y_offset,
            dz_mm=bottle_dz + body_grasp_z_offset,
            fkin=dsr["fkin"],
            ikin=dsr["ikin"],
            get_solution_space=dsr["get_solution_space"],
        )
        cup_side_joint = list(cfg.get(
            "cup_side_joint",
            [19.84, 35.26, 116.6, 106.22, 81.39, -63.12],
        ))
        _default_pour_tilt_joint = list(cup_side_joint)
        _default_pour_tilt_joint[5] = -180.12
        cup_pour_tilt_joint = list(cfg.get(
            "cup_pour_tilt_joint",
            _default_pour_tilt_joint,
        ))

        align_jvel = float(cfg.get("pour_j6_pre_rotate_vel", 10.0))
        align_jacc = float(cfg.get("pour_j6_pre_rotate_acc", 10.0))
        pour_j6_restore_vel = float(cfg.get("pour_j6_restore_vel", 60.0))
        pour_j6_restore_acc = float(cfg.get("pour_j6_restore_acc", 60.0))

        pour_tilt_delta = float(
            cfg.get(
                "pour_tilt_delta_j6_deg",
                cup_pour_tilt_joint[5] - cup_side_joint[5],
            )
        )
        pour_fast_zone = float(cfg.get("pour_fast_zone_deg", 30.0))
        pour_fast_jvel = float(cfg.get("pour_fast_joint_vel", 30.0))
        pour_fast_jacc = float(cfg.get("pour_fast_joint_acc", 30.0))

        grasp_vel = list(cfg.get("grasp_vel", [15, 10]))
        grasp_acc = list(cfg.get("grasp_acc", [30, 15]))
        fast_vel = list(cfg.get("fast_vel", [80, 60]))
        fast_acc = list(cfg.get("fast_acc", [200, 150]))
        fast_jvel = float(cfg.get("fast_joint_vel", 60.0))
        fast_jacc = float(cfg.get("fast_joint_acc", 60.0))
        pour_jvel = float(cfg.get("pour_joint_vel", 8.0))
        pour_jacc = float(cfg.get("pour_joint_acc", 8.0))

        body_grip_force = float(cfg.get("body_grip_force", 110.0))
        body_grip_width = int(cfg.get("body_grip_width_units", 0))
        body_grasp_settle = float(cfg.get("body_grasp_settle_sec", 4.5))
        pour_duration = float(cfg.get("pour_duration_sec", 3.0))
        pre_pause = float(cfg.get("pre_pour_pause_sec", 0.5))

        # J6 기울임 — align 후 티칭 J6 절대 목표 (cup_side → cup_pour_tilt)
        _upright_j6 = cup_side_joint[5]
        _tilted_j6 = cup_pour_tilt_joint[5]
        _tilt_fast_delta = math.copysign(pour_fast_zone, pour_tilt_delta)
        _fast_mid_j6 = _normalize_joint_angle(_upright_j6 + _tilt_fast_delta)

        def _fkin_tcp(joints: list[float]) -> list[float]:
            return [float(v) for v in dsr["fkin"](joints)]

        def _release_compliance() -> None:
            try:
                dsr["release_compliance_ctrl"]()
            except Exception:
                pass

        def _prepare_start() -> None:
            """open_bottle 직후 상태 가정 — home 재이동 없이 초기화만."""
            _release_compliance()
            motion.clear_cancel()
            motion.gripper.open()

        def _approach_joint(
            joints: list[float],
            label: str,
        ) -> None:
            """TCP Z↑→XY→Z↓ 접근 (충돌 방지). 최종 조인트는 align 단계에서 movej로 맞춤."""
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

        def _align_joint(joints: list[float], label: str) -> None:
            """티칭 조인트 각도로 정렬 — movel 이후 J6 IK 분기 보정."""
            motion.movej_joint(
                joints, label, task,
                vel=align_jvel, acc=align_jacc,
            )

        def _move_to_body_grasp() -> None:
            _approach_joint(body_grasp_joint, "move_body_grasp")

        def _align_body_grasp() -> None:
            _align_joint(body_grasp_joint, "align_body_grasp")

        def _grasp_body() -> None:
            """물병 몸통 약파지 — 닫힘 명령 후 충분히 대기한 뒤 다음 단계로."""
            motion.publish_status(
                task, "grasp_body", "running",
                f"몸통 파지 중 (닫힘 대기 {body_grasp_settle:.1f}초)",
            )
            motion.gripper.grip(
                force=body_grip_force,
                width_units=body_grip_width,
                wait_sec=body_grasp_settle,
            )
            motion.publish_status(
                task, "grasp_body", "done",
                f"그리퍼 닫힘 대기 완료 ({body_grasp_settle:.1f}초)",
            )

        def _carry_to_joint(
            joints: list[float],
            label: str,
            *,
            vel: list[float] | None = None,
            acc: list[float] | None = None,
            lower_vel: list[float] | None = None,
            lower_acc: list[float] | None = None,
        ) -> None:
            """목표 조인트 TCP 기준 Z↑→XY→Z↓ 이송 (파지 후 자세 유지)."""
            tcp = _fkin_tcp(joints)
            motion.carry_to_pose(
                tcp, label, task, lift,
                vel=vel or fast_vel, acc=fast_acc,
                lower_vel=lower_vel or grasp_vel,
                lower_acc=lower_acc or grasp_acc,
                keep_orientation=True,
            )

        def _carry_to_cup() -> None:
            _carry_to_joint(cup_side_joint, "carry_to_cup")

        def _align_cup_joints() -> None:
            _align_joint(cup_side_joint, "align_cup_joints")

        def _move_j6_to(
            target_j6: float,
            label: str,
            vel: float,
            acc: float,
        ) -> None:
            """align 직후 J1–J5는 cup_side 티칭값, J6만 절대 각도로 이동.

            normalize 금지: -180.12 → 179.88 변환 시 DSR movej가
            양수 방향(+243°)으로 돌아 기울임 반전됨. 원본 부호 유지.
            """
            base = list(cup_side_joint)
            base[5] = float(target_j6)
            motion.movej_joint(base, label, task, vel=vel, acc=acc)

        def _pour_tilt_fast() -> None:
            """입구 누수 방지: cup_side J6 → 중간 각도 빠르게."""
            _move_j6_to(
                _fast_mid_j6, "pour_tilt_fast", pour_fast_jvel, pour_fast_jacc,
            )

        def _pour_tilt_slow() -> None:
            """중간 각도 → cup_pour_tilt_joint J6 천천히."""
            _move_j6_to(
                _tilted_j6, "pour_tilt_slow", pour_jvel, pour_jacc,
            )

        def _hold_pour() -> None:
            motion.publish_status(task, "hold_pour", "running",
                                  f"{pour_duration:.1f}초간 따르기")
            motion.interruptible_sleep(pour_duration)
            motion.publish_status(task, "hold_pour", "done")

        def _untilt_fast() -> None:
            """최대 기울임 → 중간 각도 빠르게 (입구 통과)."""
            _move_j6_to(
                _fast_mid_j6, "untilt_fast", pour_fast_jvel, pour_fast_jacc,
            )

        def _untilt_slow() -> None:
            """중간 각도 → cup_side_joint J6 천천히."""
            _move_j6_to(
                _upright_j6, "untilt_slow", pour_jvel, pour_jacc,
            )

        def _carry_back() -> None:
            """컵홀더 복귀: body_grasp XY 정렬 후 Z만 수직 하강."""
            tcp = _fkin_tcp(body_grasp_joint)
            cur = motion.get_current_tcp_pose()
            travel_z = max(cur[2], tcp[2]) + lift
            motion.move_vertical_to_z(
                travel_z, cur, "carry_back_lift", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.move_task_pose(
                [tcp[0], tcp[1], travel_z, tcp[3], tcp[4], tcp[5]],
                "carry_back_travel", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.move_vertical_to_z(
                tcp[2],
                [tcp[0], tcp[1], travel_z, tcp[3], tcp[4], tcp[5]],
                "carry_back_lower", task,
                vel=grasp_vel, acc=grasp_acc,
            )

        def _retract_to_home() -> None:
            """Z↑ → home XY 상공 → home 조인트 (J6는 유지)."""
            cur = motion.get_current_tcp_pose()
            home_tcp = _fkin_tcp(home_joint)
            travel_z = max(cur[2], home_tcp[2]) + lift
            motion.move_vertical_to_z(
                travel_z, cur, "home_lift", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.move_task_pose(
                [home_tcp[0], home_tcp[1], travel_z,
                 cur[3], cur[4], cur[5]],
                "home_travel", task,
                vel=fast_vel, acc=fast_acc,
            )
            joints = motion.get_current_joint()
            target = list(home_joint)
            target[5] = joints[5]
            motion.movej_joint(target, "home_finish", task,
                             vel=fast_jvel, acc=fast_jacc)

        def _restore_j6_at_home() -> None:
            """홈 위치에서 J6만 복원."""
            joints = motion.get_current_joint()
            target = list(joints)
            target[5] = _normalize_joint_angle(home_joint[5])
            motion.publish_status(
                task, "restore_j6_at_home", "running",
                f"J6 복원 (목표={home_joint[5]:.1f}°)",
            )
            motion.movej_joint(
                target, "restore_j6_at_home", task,
                vel=pour_j6_restore_vel, acc=pour_j6_restore_acc,
            )
            motion.publish_status(task, "restore_j6_at_home", "done")

        steps = [
            ("prepare_start",           _prepare_start),
            ("move_body_grasp",         _move_to_body_grasp),
            ("align_body_grasp",        _align_body_grasp),
            ("grasp_body",              _grasp_body),
            ("carry_to_cup",            _carry_to_cup),
            ("align_cup_joints",        _align_cup_joints),
            ("pre_pour_pause",          lambda: motion.interruptible_sleep(pre_pause)),
            ("pour_tilt_fast",          _pour_tilt_fast),
            ("pour_tilt_slow",          _pour_tilt_slow),
            ("hold_pour",               _hold_pour),
            ("untilt_fast",             _untilt_fast),
            ("untilt_slow",             _untilt_slow),
            ("carry_back",              _carry_back),
            ("release_body",            motion.gripper.open),
            ("retract_to_home",         _retract_to_home),
            ("restore_j6_at_home",      _restore_j6_at_home),
        ]
        motion.run_sequence(task, steps)
