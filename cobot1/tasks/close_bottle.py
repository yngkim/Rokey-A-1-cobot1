"""페트병 뚜껑 닫기 (닫기 + 물 원위치 복귀) — open_bottle 의 역순.

전제:
  뚜껑이 open_bottle 이 바닥에 내려놓은 위치에 있고, 물병은 컵홀더에
  개봉된 채 꽂혀 있으며, 로봇은 home.
  (바닥 파지 위치는 open_bottle 이 저장한 TCP 포즈를 우선 사용)

흐름:
  home → 바닥 뚜껑 집기 → 수직 들어올림
  → 조임 직전 포즈 XY 맞춤 → Z 하강해 티칭 포즈 도달
  → 회전(조임)+동시 하강으로 닫기 → 추가 1회 조임
  → 그리퍼 열기 → 다시 닫아 재파지 → 닫힌 물병을 초기 위치로 이송 → home 복귀

티칭: water_poses.cupholder_cap_close_start(조임 직전), water_cap_grasp(초기 물통).
"""

from __future__ import annotations

from cobot1.motion.pose_utils import offset_pose_z
from cobot1.runtime_state import load_cap_place_pose
from cobot1.tasks.base import BaseTask


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
        pos_water_cap = offset_pose_z(wp["water_cap_grasp"], bottle_dz)                  # pos1
        pos_cupholder_cap = offset_pose_z(wp["cupholder_cap_grasp"], bottle_dz)          # pos2
        pos_screw_start = offset_pose_z(wp["cupholder_cap_close_start"], bottle_dz)      # 조임 직전 TCP
        lift = float(wp.get("lift_clearance_mm", 120.0))

        grasp_vel = list(cfg.get("grasp_vel", [15, 10]))   # 섬세 작업(느림)
        grasp_acc = list(cfg.get("grasp_acc", [30, 15]))
        fast_vel  = list(cfg.get("fast_vel", [80, 60]))    # 일반 이동(빠름)
        fast_acc  = list(cfg.get("fast_acc", [200, 150]))
        fast_jvel = float(cfg.get("fast_joint_vel", 60.0))
        fast_jacc = float(cfg.get("fast_joint_acc", 60.0))

        floor_z          = float(cfg.get("cap_place_floor_z_mm", 237.0))
        floor_pick_extra = float(cfg.get("floor_pick_extra_mm", 5.0))
        twist_angle      = float(cfg["twist_angle_deg"])
        twist_steps      = int(cfg["twist_steps"])
        twist_rise       = float(cfg.get("twist_rise_mm", 0.0))
        grip_force       = float(cfg.get("grip_force", 100.0))      # 바닥 뚜껑 약파지
        grasp_settle     = float(cfg.get("grasp_settle_sec", 2.0))  # 파지 완료 대기(상승 전)
        regrasp_force    = float(cfg.get("regrasp_force", 400.0))   # 이송 전 강파지

        # 닫기 회전: open 보다 2스텝 적게 조여 과조임 외력 정지 방지
        step_angle  = twist_angle / twist_steps if twist_steps else 0.0
        close_steps = max(1, twist_steps - 2)
        close_angle = -step_angle * close_steps            # 조임 방향(개봉 반대)
        close_rise  = (twist_rise / twist_steps * close_steps) if twist_steps else 0.0

        from cobot1.motion.dsr_imports import import_dsr_api
        home_tcp = [float(v) for v in import_dsr_api()["fkin"](home_joint)]

        saved_place = load_cap_place_pose()
        if saved_place is not None:
            cap_floor_pick = list(saved_place)
            cap_floor_pick[2] -= floor_pick_extra
            pick_source = "saved"
        else:
            cap_floor_pick = [
                home_tcp[0] + 0.0, home_tcp[1] - 100.0, floor_z - floor_pick_extra,
                pos_cupholder_cap[3], pos_cupholder_cap[4], pos_cupholder_cap[5],
            ]
            pick_source = "computed"
        motion.publish_status(
            task, "cap_pick_pose", "done",
            f"바닥 뚜껑 파지 포즈({pick_source}): "
            f"x={cap_floor_pick[0]:.1f}, y={cap_floor_pick[1]:.1f}, z={cap_floor_pick[2]:.1f}",
        )

        # --- (주석) 병 입구 위 떨어뜨려 자기정렬 후 재파지 방식 ---
        # drop_clearance = float(cfg.get("drop_clearance_mm", 10.0))
        # cap_drop_pose = [
        #     pos_cupholder_cap[0], pos_cupholder_cap[1],
        #     pos_cupholder_cap[2] + drop_clearance,
        #     pos_cupholder_cap[3], pos_cupholder_cap[4], pos_cupholder_cap[5],
        # ]

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
            """바닥 뚜껑 바로 위(수직 상공)로만 이동 — 자세 정렬, 아직 하강 X."""
            cur = motion.get_current_tcp_pose()
            travel_z = max(cur[2], cap_floor_pick[2]) + lift
            above = [
                cap_floor_pick[0], cap_floor_pick[1], travel_z,
                cap_floor_pick[3], cap_floor_pick[4], cap_floor_pick[5],
            ]
            motion.move_task_pose(above, "approach_floor_cap", task,
                                  vel=fast_vel, acc=fast_acc)

        def _descend_to_floor_cap() -> None:
            """바닥 뚜껑 파지 위치까지 베이스 Z 수직 하강."""
            motion.move_task_pose(cap_floor_pick, "descend_to_floor_cap", task,
                                  vel=grasp_vel, acc=grasp_acc)

        def _grasp_cap_gently() -> None:
            """뚜껑을 약하게 파지 — 파지 중 팔 정지."""
            motion.gripper.grip(force=grip_force)

        def _grasp_settle() -> None:
            """파지 완료까지 대기 후 상승."""
            motion.publish_status(task, "grasp_settle", "running",
                                  f"파지 완료 대기 {grasp_settle:.1f}초")
            motion.interruptible_sleep(grasp_settle)
            motion.publish_status(task, "grasp_settle", "done")

        def _lift_cap_off_floor() -> None:
            """파지 후 베이스 Z 로만 수직 상승."""
            motion.move_base_z_delta(lift, "lift_cap_off_floor", task,
                                     vel=fast_vel, acc=fast_acc)

        def _approach_screw_xy() -> None:
            """조임 직전 포즈 XY·자세 맞춤 — 충분한 높이에서 수평 이동만."""
            cur = motion.get_current_tcp_pose()
            travel_z = max(cur[2], pos_screw_start[2]) + lift
            target = [
                pos_screw_start[0], pos_screw_start[1], travel_z,
                pos_screw_start[3], pos_screw_start[4], pos_screw_start[5],
            ]
            motion.move_task_pose(target, "approach_screw_xy", task,
                                  vel=fast_vel, acc=fast_acc)

        def _descend_to_screw_start() -> None:
            """XY 맞춘 뒤 Z 만 내려 조임 직전 티칭 포즈로 도달."""
            motion.move_task_pose(pos_screw_start, "descend_to_screw_start", task,
                                  vel=grasp_vel, acc=grasp_acc)

        # --- (주석) 떨어뜨려 자기정렬 ---
        # def _carry_over_bottle() -> None:
        #     motion.carry_to_pose(cap_drop_pose, "carry_over_bottle", task, lift, ...)
        # def _prerotate_cap() -> None: ...
        # def _descend_to_drop() -> None: ...
        # def _lower_to_regrasp() -> None: ...

        def _screw_close() -> None:
            """회전(조임)+동시 하강으로 닫기 — open 보다 2스텝 적게."""
            motion.rotate_tool_z_steps(
                close_angle,
                close_steps,
                "screw",
                task,
                pause_sec=0.0,
                rise_total_mm=-close_rise,
                vel=grasp_vel,
                acc=grasp_acc,
            )

        def _screw_close_extra() -> None:
            """조임 1회 추가 — 나사산 한 스텝 더 조임."""
            extra_angle = -step_angle
            extra_rise = (twist_rise / twist_steps) if twist_steps else 0.0
            motion.rotate_tool_z_steps(
                extra_angle,
                1,
                "screw_extra",
                task,
                pause_sec=0.0,
                rise_total_mm=-extra_rise,
                vel=grasp_vel,
                acc=grasp_acc,
            )

        def _regrasp_for_carry() -> None:
            """조임 후 그리퍼 열었다가 다시 닫아 이송용으로 재파지."""
            motion.gripper.open()
            motion.gripper.grip(force=regrasp_force)

        # def _regrasp_firm() -> None:
        #     """이송 전 뚜껑 강파지 — 미끄럼 방지."""
        #     motion.gripper.grip(force=regrasp_force)

        def _carry_water_to_initial() -> None:
            """닫힌 물병을 초기 위치로 이송."""
            motion.carry_to_pose(
                pos_water_cap, "carry_water_to_initial", task, lift,
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
            ("lift_cap_off_floor",      _lift_cap_off_floor),
            ("approach_screw_xy",       _approach_screw_xy),
            ("descend_to_screw_start",  _descend_to_screw_start),
            ("screw_close",             _screw_close),
            ("screw_close_extra",       _screw_close_extra),
            ("regrasp_for_carry",       _regrasp_for_carry),
            # ("regrasp_firm",            _regrasp_firm),
            ("carry_water_to_initial",  _carry_water_to_initial),
            ("release_cap",             motion.gripper.open),
            ("retract_and_home",        _retract_and_home),
        ]
        motion.run_sequence(task, steps)
