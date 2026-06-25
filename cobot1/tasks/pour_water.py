"""컵에 물 따르기 (몸통 파지 + J6 구간별 기울여 붓기).

전제:
  open_bottle 직후 — 로봇은 home, 그리퍼 열림, 물병은 컵홀더에 개봉된 채 꽂혀 있음.

흐름:
  몸통 파지   → 컵 옆 이동 → J6 빠름(0↔±30) → 느림(±30↔±80) 기울임 → 유지
  → 약한 재파지 → J6 빠름(±80↔±50) → 느림(±50↔0) 세움 → 컵홀더 복귀 → home
  (close_bottle 시작 전 상태)
"""

from __future__ import annotations

import math

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


class PourWaterTask(BaseTask):
    name = "pour_water"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        motion.set_recovery_joint(home_joint)

        from cobot1.motion.dsr_imports import import_dsr_api

        wp = self._scenarios["water_poses"]
        lift = float(wp.get("lift_clearance_mm", 120.0))

        body_grasp_joint = list(cfg.get(
            "body_grasp_joint",
            [-42.44, 44.58, 101.47, 52.00, 112.40, -63.81],
        ))
        cup_side_joint = list(cfg.get(
            "cup_side_joint",
            [19.84, 35.26, 116.6, 106.22, 81.39, -63.12],
        ))
        pour_tilt_delta = float(cfg.get("pour_tilt_delta_j6_deg", -80.0))
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

        body_grip_force = float(cfg.get("body_grip_force", 100.0))
        body_grip_width = int(cfg.get("body_grip_width_units", 0))
        body_grip_force_after = float(cfg.get("body_grip_force_after_pour", 80.0))
        body_grip_relax_wait = float(cfg.get("body_grip_relax_wait_sec", 1.0))
        body_grasp_settle = float(cfg.get("body_grasp_settle_sec", 4.5))
        pour_duration = float(cfg.get("pour_duration_sec", 3.0))
        pre_pause = float(cfg.get("pre_pour_pause_sec", 0.5))

        # J6 구간별 기울임 waypoint (pour_tilt_delta 부호에 맞춤)
        _tilt_fast_delta = math.copysign(pour_fast_zone, pour_tilt_delta)
        _tilt_mid_delta = pour_tilt_delta + math.copysign(pour_fast_zone, -pour_tilt_delta)

        def _fkin_tcp(joints: list[float]) -> list[float]:
            return [float(v) for v in import_dsr_api()["fkin"](joints)]

        def _release_compliance() -> None:
            try:
                import_dsr_api()["release_compliance_ctrl"]()
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
            """빈 그리퍼로 목표 조인트에 TCP Z↑→XY→Z↓ 접근 (세워진 물병 충돌 방지)."""
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

        def _move_to_body_grasp() -> None:
            _approach_joint(body_grasp_joint, "move_body_grasp")

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
            keep_orientation: bool = False,
        ) -> None:
            """목표 조인트의 TCP 기준 Z↑→XY→Z↓ 이송."""
            tcp = _fkin_tcp(joints)
            motion.carry_to_pose(
                tcp, label, task, lift,
                vel=vel or fast_vel, acc=acc or fast_acc,
                lower_vel=lower_vel or grasp_vel,
                lower_acc=lower_acc or grasp_acc,
                keep_orientation=keep_orientation,
            )

        def _carry_to_cup() -> None:
            _carry_to_joint(cup_side_joint, "carry_to_cup")

        def _move_j6_delta(
            delta_deg: float,
            label: str,
            vel: float,
            acc: float,
        ) -> None:
            target = _joint_with_j6_delta(cup_side_joint, delta_deg)
            motion.movej_joint(target, label, task, vel=vel, acc=acc)

        def _pour_tilt_fast() -> None:
            """입구 누수 방지: 0 → ±fast_zone 빠르게."""
            _move_j6_delta(_tilt_fast_delta, "pour_tilt_fast", pour_fast_jvel, pour_fast_jacc)

        def _pour_tilt_slow() -> None:
            """±fast_zone → 최대 기울임 천천히."""
            _move_j6_delta(pour_tilt_delta, "pour_tilt_slow", pour_jvel, pour_jacc)

        def _hold_pour() -> None:
            motion.publish_status(task, "hold_pour", "running",
                                  f"{pour_duration:.1f}초간 따르기")
            motion.interruptible_sleep(pour_duration)
            motion.publish_status(task, "hold_pour", "done")

        def _relax_grip_after_pour() -> None:
            """빈 병 과조임 방지 — 벌리지 않고 힘만 ~8N(80)으로 낮춤."""
            motion.publish_status(
                task, "relax_grip", "running",
                f"힘만 낮춤 (force={body_grip_force_after:.0f}, width=0)",
            )
            motion.gripper.grip(
                force=body_grip_force_after,
                width_units=0,
                wait_sec=body_grip_relax_wait,
            )
            motion.publish_status(task, "relax_grip", "done")

        def _untilt_fast() -> None:
            """±80 → ±60 빠르게 (입구 통과)."""
            _move_j6_delta(_tilt_mid_delta, "untilt_fast", pour_fast_jvel, pour_fast_jacc)

        def _untilt_slow() -> None:
            """±60 → 0 천천히."""
            _move_j6_delta(0.0, "untilt_slow", pour_jvel, pour_jacc)

        def _carry_back() -> None:
            _carry_to_joint(
                body_grasp_joint, "carry_back",
                keep_orientation=True,
            )

        def _retract_and_home() -> None:
            """세워진 물병 회피: Z↑ → home XY 상공 → home 조인트."""
            cur = motion.get_current_tcp_pose()
            home_tcp = _fkin_tcp(home_joint)
            travel_z = max(cur[2], home_tcp[2]) + lift
            motion.move_vertical_to_z(
                travel_z, cur, "home_lift", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.move_task_pose(
                [home_tcp[0], home_tcp[1], travel_z,
                 home_tcp[3], home_tcp[4], home_tcp[5]],
                "home_travel", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.movej_joint(home_joint, "home_finish", task,
                             vel=fast_jvel, acc=fast_jacc)

        steps = [
            ("prepare_start",    _prepare_start),
            ("move_body_grasp",  _move_to_body_grasp),
            ("grasp_body",       _grasp_body),
            ("carry_to_cup",     _carry_to_cup),
            ("pre_pour_pause",   lambda: motion.interruptible_sleep(pre_pause)),
            ("pour_tilt_fast",   _pour_tilt_fast),
            ("pour_tilt_slow",   _pour_tilt_slow),
            ("hold_pour",        _hold_pour),
            ("relax_grip",       _relax_grip_after_pour),
            ("untilt_fast",      _untilt_fast),
            ("untilt_slow",      _untilt_slow),
            ("carry_back",       _carry_back),
            ("release_body",     motion.gripper.open),
            ("retract_and_home", _retract_and_home),
        ]
        motion.run_sequence(task, steps)
