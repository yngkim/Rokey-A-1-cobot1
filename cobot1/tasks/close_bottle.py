"""페트병 뚜껑 닫기 (닫기 + 물 원위치 복귀) — open_bottle 의 역순.

전제:
  뚜껑이 open_bottle 이 바닥에 내려놓은 위치에 있고, 물병은 컵홀더에
  개봉된 채 꽂혀 있으며, 로봇은 home.
  (바닥 파지 위치는 open_bottle 이 저장한 TCP 포즈를 우선 사용)

흐름:
  home → 바닥 뚜껑 집기 → Z↑ → Y → X → Z↓ 조임 위치
  → 살살 놓기 → Z↑ → 빈 그리퍼 닫기 → 뚜껑 중앙 누르기(ΔFz 40N)
  → 그리퍼 열기 → 재하강·재파지 → J6 가드 조임 → 물병 이송 → home

티칭: water_poses.cupholder_cap_close_start(조임 직전), water_cap_grasp(초기 물통).
"""

from __future__ import annotations

from cobot1.motion.pose_utils import offset_pose_z
from cobot1.runtime_state import load_cap_place_pose
from cobot1.tasks.base import BaseTask


def _normalize_joint_angle(deg: float) -> float:
    while deg > 180.0:
        deg -= 360.0
    while deg < -180.0:
        deg += 360.0
    return deg


class CloseBottleTask(BaseTask):
    name = "close_bottle"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        motion.set_recovery_joint(home_joint)

        wp = self._scenarios["water_poses"]
        bottle_dz = float(wp.get("bottle_height_offset_mm", 0.0))
        cap_grasp_extra = float(wp.get("cap_grasp_extra_descent_mm", 0.0))
        pos_water_cap = offset_pose_z(wp["water_cap_grasp"], bottle_dz)
        pos_cupholder_cap = offset_pose_z(wp["cupholder_cap_grasp"], bottle_dz)
        screw_start_offset_x = float(cfg.get("screw_start_offset_x_mm", -3.0))
        screw_start_offset_y = float(cfg.get("screw_start_offset_y_mm", 3.0))
        lift = float(wp.get("lift_clearance_mm", 120.0))

        grasp_vel = list(cfg.get("grasp_vel", [15, 10]))
        grasp_acc = list(cfg.get("grasp_acc", [30, 15]))
        fast_vel = list(cfg.get("fast_vel", [80, 60]))
        fast_acc = list(cfg.get("fast_acc", [200, 150]))
        fast_jvel = float(cfg.get("fast_joint_vel", 60.0))
        fast_jacc = float(cfg.get("fast_joint_acc", 60.0))

        floor_z = float(cfg.get("cap_place_floor_z_mm", 237.0))
        floor_pick_extra = float(cfg.get("floor_pick_extra_mm", 5.0))
        floor_pick_raise = float(cfg.get("floor_pick_raise_mm", 2.0))
        water_place_z = float(cfg.get("water_place_offset_z_mm", 5.0))
        place_water_cap = offset_pose_z(pos_water_cap, water_place_z)
        twist_angle = float(cfg["twist_angle_deg"])
        twist_steps = int(cfg["twist_steps"])
        twist_rise = float(cfg.get("twist_rise_mm", 0.0))
        screw_close_add = int(cfg.get("screw_close_add_steps", 0))
        grip_force = float(cfg.get("grip_force", 100.0))
        grasp_settle = float(cfg.get("grasp_settle_sec", 2.0))
        regrasp_force = float(cfg.get("regrasp_force", 400.0))

        cap_preseat_open_force = float(cfg.get("cap_preseat_open_force", 80.0))
        cap_preseat_open_steps = int(cfg.get("cap_preseat_open_steps", 6))
        cap_preseat_open_pause = float(cfg.get("cap_preseat_open_pause_sec", 0.4))
        preseat_lift = float(cfg.get("cap_preseat_lift_mm", 80.0))
        press_approach_z = float(cfg.get("cap_press_approach_z_mm", 25.0))
        press_threshold_z = float(cfg.get("cap_press_force_threshold_z", 35.0))
        press_max_force_z = float(cfg.get("cap_press_max_force_z", 38.0))
        press_step_mm = float(cfg.get("cap_press_step_mm", 0.3))
        press_vel = list(cfg.get("cap_press_vel", [3, 2]))
        press_acc = list(cfg.get("cap_press_acc", [6, 4]))
        press_max_travel = float(cfg.get("cap_press_max_travel_mm", 40.0))
        cap_screw_grasp_force = float(cfg.get("cap_screw_grasp_force", 400.0))
        cap_screw_grasp_wait = float(cfg.get("cap_screw_grasp_wait_sec", 2.0))
        screw_j6_abs_limit = float(cfg.get("screw_j6_abs_limit_deg", 170.0))
        screw_j6_delta_limit = float(cfg.get("screw_j6_delta_limit_deg", 120.0))
        screw_j6_restore = float(cfg.get("screw_j6_restore_deg", 249.24))
        screw_j6_unwind_vel = float(cfg.get("screw_j6_unwind_joint_vel", 15.0))

        step_angle = twist_angle / twist_steps if twist_steps else 0.0
        close_steps = max(1, twist_steps - 2 + screw_close_add)
        close_angle = -step_angle * close_steps
        close_rise = (twist_rise / twist_steps * close_steps) if twist_steps else 0.0

        from cobot1.motion.dsr_imports import import_dsr_api
        dsr = import_dsr_api()
        home_tcp = [float(v) for v in dsr["fkin"](home_joint)]
        pos_screw_close = offset_pose_z(
            wp["cupholder_cap_close_start"],
            bottle_dz - cap_grasp_extra,
        )
        screw_target = list(pos_screw_close)
        screw_target[0] += screw_start_offset_x
        screw_target[1] += screw_start_offset_y

        saved_place = load_cap_place_pose()
        if saved_place is not None:
            cap_floor_pick = list(saved_place)
            cap_floor_pick[2] -= floor_pick_extra + cap_grasp_extra
            cap_floor_pick[2] += floor_pick_raise
            pick_source = "saved"
        else:
            cap_floor_pick = [
                home_tcp[0] + 0.0, home_tcp[1] - 100.0,
                floor_z - floor_pick_extra - cap_grasp_extra + floor_pick_raise,
                pos_cupholder_cap[3], pos_cupholder_cap[4], pos_cupholder_cap[5],
            ]
            pick_source = "computed"
        motion.publish_status(
            task, "cap_pick_pose", "done",
            f"바닥 뚜껑 파지 포즈({pick_source}): "
            f"x={cap_floor_pick[0]:.1f}, y={cap_floor_pick[1]:.1f}, z={cap_floor_pick[2]:.1f}",
        )

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

        def _approach_floor_cap() -> None:
            cur = motion.get_current_tcp_pose()
            travel_z = max(cur[2], cap_floor_pick[2]) + lift
            above = [
                cap_floor_pick[0], cap_floor_pick[1], travel_z,
                cap_floor_pick[3], cap_floor_pick[4], cap_floor_pick[5],
            ]
            motion.move_task_pose(above, "approach_floor_cap", task,
                                  vel=fast_vel, acc=fast_acc)

        def _descend_to_floor_cap() -> None:
            motion.move_task_pose(cap_floor_pick, "descend_to_floor_cap", task,
                                  vel=grasp_vel, acc=grasp_acc)

        def _grasp_cap_gently() -> None:
            motion.gripper.grip(force=grip_force)

        def _grasp_settle() -> None:
            motion.publish_status(task, "grasp_settle", "running",
                                  f"파지 완료 대기 {grasp_settle:.1f}초")
            motion.interruptible_sleep(grasp_settle)
            motion.publish_status(task, "grasp_settle", "done")

        def _carry_cap_to_screw() -> None:
            cur = motion.get_current_tcp_pose()
            travel_z = max(cur[2], screw_target[2]) + lift
            motion.move_vertical_to_z(
                travel_z, cur, "screw_travel_lift", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.move_task_pose(
                [cur[0], screw_target[1], travel_z, cur[3], cur[4], cur[5]],
                "screw_travel_y", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.move_task_pose(
                [screw_target[0], screw_target[1], travel_z,
                 cur[3], cur[4], cur[5]],
                "screw_travel_x", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.move_task_pose(
                screw_target, "screw_descend", task,
                vel=grasp_vel, acc=grasp_acc,
            )

        def _soft_release_cap() -> None:
            motion.gripper.open_slow(
                force=cap_preseat_open_force,
                steps=cap_preseat_open_steps,
                step_pause_sec=cap_preseat_open_pause,
            )

        def _preseat_lift() -> None:
            motion.move_base_z_delta(
                preseat_lift, "preseat_lift", task,
                vel=fast_vel, acc=fast_acc,
            )

        def _close_empty_gripper() -> None:
            motion.gripper.close()

        def _press_cap_center() -> None:
            """빈 그리퍼로 뚜껑 중앙을 천천히 눌러 정렬 (ΔFz 35N에서 정지)."""
            press_anchor = list(screw_target)
            press_anchor[2] = screw_target[2] + press_approach_z
            motion.move_task_pose(
                press_anchor, "press_approach", task,
                vel=grasp_vel, acc=grasp_acc,
            )
            motion.pause_safety_force_abort()
            try:
                baseline = motion.safety.sample_force_baseline()
                motion.probe_down_until_contact(
                    task,
                    press_anchor,
                    baseline,
                    force_threshold_z=press_threshold_z,
                    max_travel_mm=press_max_travel,
                    step_mm=press_step_mm,
                    coarse_step_mm=press_step_mm,
                    coarse_travel_mm=0.0,
                    max_force_z=press_max_force_z,
                    vel=press_vel,
                    acc=press_acc,
                    fine_vel=press_vel,
                    fine_acc=press_acc,
                )
            finally:
                motion.resume_safety_force_abort()

        def _open_for_regrasp() -> None:
            motion.gripper.open()

        def _descend_for_screw() -> None:
            motion.move_task_pose(
                screw_target, "descend_for_screw", task,
                vel=grasp_vel, acc=grasp_acc,
            )

        def _regrasp_for_screw() -> None:
            motion.gripper.grip(
                force=cap_screw_grasp_force,
                wait_sec=cap_screw_grasp_wait,
            )

        def _screw_j6_unwind() -> None:
            motion.publish_status(
                task, "screw_j6_unwind", "running",
                f"J6 복원 (목표={screw_j6_restore:.1f}°)",
            )
            motion.gripper.open()
            joints = motion.get_current_joint()
            joints[5] = _normalize_joint_angle(screw_j6_restore)
            motion.movej_joint(
                joints, "screw_j6_unwind", task,
                vel=screw_j6_unwind_vel, acc=screw_j6_unwind_vel,
            )
            motion.gripper.grip(
                force=cap_screw_grasp_force,
                wait_sec=cap_screw_grasp_wait,
            )
            motion.publish_status(task, "screw_j6_unwind", "done")

        def _screw_close() -> None:
            motion.rotate_tool_z_steps_guarded(
                close_angle,
                close_steps,
                "screw",
                task,
                pause_sec=0.0,
                rise_total_mm=-close_rise,
                vel=grasp_vel,
                acc=grasp_acc,
                j6_abs_limit_deg=screw_j6_abs_limit,
                j6_delta_limit_deg=screw_j6_delta_limit,
                on_j6_unwind=_screw_j6_unwind,
            )

        def _screw_close_extra() -> None:
            extra_angle = -step_angle
            extra_rise = (twist_rise / twist_steps) if twist_steps else 0.0
            motion.rotate_tool_z_steps_guarded(
                extra_angle,
                1,
                "screw_extra",
                task,
                pause_sec=0.0,
                rise_total_mm=-extra_rise,
                vel=grasp_vel,
                acc=grasp_acc,
                j6_abs_limit_deg=screw_j6_abs_limit,
                j6_delta_limit_deg=screw_j6_delta_limit,
                on_j6_unwind=_screw_j6_unwind,
            )

        def _regrasp_for_carry() -> None:
            motion.gripper.open()
            motion.gripper.grip(force=regrasp_force)

        def _carry_water_to_initial() -> None:
            motion.carry_to_pose(
                place_water_cap, "carry_water_to_initial", task, lift,
                vel=fast_vel, acc=fast_acc,
                lower_vel=grasp_vel, lower_acc=grasp_acc,
            )

        def _retract_and_home() -> None:
            motion.move_base_z_delta(lift, "retract", task,
                                     vel=fast_vel, acc=fast_acc)
            motion.movej_joint(home_joint, "home_finish", task,
                               vel=fast_jvel, acc=fast_jacc)

        steps = [
            ("prepare_home",            _prepare_home),
            ("approach_floor_cap",      _approach_floor_cap),
            ("descend_to_floor_cap",    _descend_to_floor_cap),
            ("grasp_cap",               _grasp_cap_gently),
            ("grasp_settle",            _grasp_settle),
            ("carry_cap_to_screw",      _carry_cap_to_screw),
            ("soft_release_cap",        _soft_release_cap),
            ("preseat_lift",            _preseat_lift),
            ("close_empty_gripper",     _close_empty_gripper),
            ("press_cap_center",        _press_cap_center),
            ("open_for_regrasp",        _open_for_regrasp),
            ("descend_for_screw",       _descend_for_screw),
            ("regrasp_for_screw",       _regrasp_for_screw),
            ("screw_close",             _screw_close),
            ("screw_close_extra",       _screw_close_extra),
            ("regrasp_for_carry",       _regrasp_for_carry),
            ("carry_water_to_initial",  _carry_water_to_initial),
            ("release_cap",             motion.gripper.open),
            ("retract_and_home",        _retract_and_home),
        ]
        motion.run_sequence(task, steps)
