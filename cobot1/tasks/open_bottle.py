"""페트병 뚜껑 열기 (물 가져오기 + 컵홀더 안착 + 재파지 개봉).

전제:
  물병이 초기 위치(water_poses.water_cap_grasp)에 세워져 있고 로봇은 home.

흐름:
  home → 초기 물통 위 접근 → 하강해 '뚜껑' 파지
  → 컵홀더로 이송(Z↑→XY→Z↓, 자세 고정)해 안착 → 그리퍼 열어 병 두기
  → 개봉 직전 포즈 XY 맞춤 → Z 하강해 재파지
  → J6 회전으로 개봉 → 5mm 하강 → 그리퍼 열기·약파지(100) 재파지 → Z 들어올리기
  → home J6 복원 → Y축 이동 → 바닥 하강 → 그리퍼 열기(바닥 안착 후만)
  → 상승 후 home 복귀

티칭:
  water_poses.water_cap_grasp(초기 물통), cupholder_cap_grasp(컵홀더),
  cupholder_cap_open_start(개봉 직전, Y=10.81).
"""

from __future__ import annotations

from cobot1.motion.pose_utils import offset_pose_z
from cobot1.runtime_state import save_cap_place_pose
from cobot1.tasks.base import BaseTask


def _normalize_joint_angle(deg: float) -> float:
    while deg > 180.0:
        deg -= 360.0
    while deg < -180.0:
        deg += 360.0
    return deg


class OpenBottleTask(BaseTask):
    name = "open_bottle"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        motion.set_recovery_joint(home_joint)

        wp = self._scenarios["water_poses"]
        bottle_dz = float(wp.get("bottle_height_offset_mm", 0.0))
        cap_grasp_extra = float(wp.get("cap_grasp_extra_descent_mm", 0.0))
        pos_water_cap = offset_pose_z(wp["water_cap_grasp"], bottle_dz - cap_grasp_extra)  # pos1
        pos_cupholder_cap = offset_pose_z(wp["cupholder_cap_grasp"], bottle_dz)      # pos2
        open_grasp_extra = float(cfg.get("open_grasp_extra_descent_mm", 0.0))
        pos_open_start = offset_pose_z(
            wp["cupholder_cap_open_start"],
            bottle_dz - open_grasp_extra - cap_grasp_extra,
        )  # 개봉 직전 TCP (재파지 높이)
        lift = float(wp.get("lift_clearance_mm", 120.0))
        holder_place_extra = float(cfg.get("holder_place_extra_mm", 6.0))
        regrasp_lift = float(cfg.get("regrasp_lift_mm", 100.0))

        cap_lift = float(cfg.get("cap_lift_mm", 30.0))
        grip_cfg = self._scenarios.get("gripper", {})
        cap_grasp_force = float(cfg.get("cap_grasp_force", grip_cfg.get("force", 400)))
        cap_grasp_force_after_open = float(cfg.get("cap_grasp_force_after_open", 100.0))
        cap_grasp_regrasp_wait = float(cfg.get("cap_grasp_regrasp_wait_sec", 2.0))
        cap_release_open_force = float(cfg.get("cap_release_open_force", 80.0))
        cap_release_open_steps = int(cfg.get("cap_release_open_steps", 6))
        cap_release_open_pause = float(cfg.get("cap_release_open_step_pause_sec", 0.4))
        pre_release_descent = float(cfg.get("pre_release_descent_mm", 5.0))
        grasp_vel = list(cfg.get("grasp_vel", [15, 10]))   # 섬세 작업(느림)
        grasp_acc = list(cfg.get("grasp_acc", [30, 15]))
        fast_vel  = list(cfg.get("fast_vel", [80, 60]))    # 일반 이동(빠름)
        fast_acc  = list(cfg.get("fast_acc", [200, 150]))
        fast_jvel = float(cfg.get("fast_joint_vel", 60.0))
        fast_jacc = float(cfg.get("fast_joint_acc", 60.0))

        floor_z = float(cfg.get("cap_place_floor_z_mm", 237.0))
        place_approach_z = float(cfg.get("cap_place_approach_z_mm", 50.0))
        cap_place_extra = float(cfg.get("cap_place_extra_descent_mm", 2.0))
        place_floor_z = floor_z - cap_place_extra
        twist_angle = float(cfg["twist_angle_deg"])

        # 뚜껑 놓을 위치: home_joint TCP 기준 X+0/Y-100 (바닥)
        from cobot1.motion.dsr_imports import import_dsr_api
        from cobot1.motion.pose_utils import flatten_pose_values

        home_tcp = flatten_pose_values(import_dsr_api()["fkin"](home_joint))
        if len(home_tcp) < 2:
            raise RuntimeError("home_joint fkin failed — cannot compute place_y")
        place_y = home_tcp[1] - 100.0

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

        def _approach_water_cap() -> None:
            """초기 물통 위에서 뚜껑 파지 포즈로 수직 접근(빈 그리퍼)."""
            motion.approach_from_above(
                pos_water_cap, "approach_water_cap", task, lift,
                vel=fast_vel, acc=fast_acc,
                descend_vel=grasp_vel, descend_acc=grasp_acc,
            )

        def _carry_to_cupholder() -> None:
            """뚜껑 쥔 채 컵홀더로 이송(Z↑→XY→Z↓, 자세 고정)해 안착."""
            motion.carry_to_pose(
                pos_cupholder_cap, "carry_to_cupholder", task, lift,
                vel=fast_vel, acc=fast_acc,
                lower_vel=grasp_vel, lower_acc=grasp_acc,
            )

        def _lower_into_holder() -> None:
            """컵홀더 안착 후 티칭 높이보다 holder_place_extra 만큼 더 하강해 놓기."""
            motion.move_base_z_delta(-holder_place_extra, "lower_into_holder", task,
                                     vel=grasp_vel, acc=grasp_acc)

        def _approach_for_reopen() -> None:
            """병 놓은 뒤 약 10cm만 올려 XY 맞춤 — 과도한 상승·재하강 방지."""
            cur = motion.get_current_tcp_pose()
            travel_z = cur[2] + regrasp_lift
            motion.move_task_pose(
                [cur[0], cur[1], travel_z, cur[3], cur[4], cur[5]],
                "lift_for_reopen", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.move_task_pose(
                [pos_open_start[0], pos_open_start[1], travel_z,
                 pos_open_start[3], pos_open_start[4], pos_open_start[5]],
                "approach_open_xy", task,
                vel=fast_vel, acc=fast_acc,
            )
            motion.gripper.open()

        # --- (주석) lift(120mm) 이중 상승 ---
        # def _retract_above_holder() -> None:
        #     motion.move_base_z_delta(lift, "retract_above_holder", task, ...)
        # def _approach_open_xy() -> None:
        #     travel_z = max(cur[2], pos_open_start[2]) + lift  # 너무 높음

        def _descend_to_open_start() -> None:
            """XY 맞춘 뒤 Z 만 내려 개봉 직전 티칭 포즈로 도달."""
            motion.move_task_pose(pos_open_start, "descend_to_open_start", task,
                                  vel=grasp_vel, acc=grasp_acc)

        # --- (주석) start_joint + grasp_descent 재파지 ---
        # def _regrasp_move_start() -> None:
        #     motion.movej_joint(start_joint, "regrasp_move_start", task, ...)
        #     motion.gripper.open()
        # def _regrasp_descend() -> None:
        #     motion.move_relative_tool([0, 0, grasp_descent, 0, 0, 0], ...)

        def _twist_open() -> None:
            motion.rotate_tool_z_steps(
                twist_angle,
                int(cfg["twist_steps"]),
                "twist",
                task,
                pause_sec=0.0,
                rise_total_mm=float(cfg.get("twist_rise_mm", 0.0)),
                vel=grasp_vel,
                acc=grasp_acc,
            )

        def _descend_before_regrasp() -> None:
            """개봉 직후 재파지 전 5mm 하강 — 뚜껑·그리퍼 정렬."""
            motion.move_base_z_delta(
                -pre_release_descent, "descend_before_regrasp", task,
                vel=grasp_vel, acc=grasp_acc,
            )

        def _release_after_open() -> None:
            """개봉 직후 그 자리에서 그리퍼를 천천히 연다 — 조임 힘 해제 후 재파지 준비."""
            motion.gripper.open_slow(
                force=cap_release_open_force,
                steps=cap_release_open_steps,
                step_pause_sec=cap_release_open_pause,
            )

        def _regrasp_cap_light() -> None:
            """개봉된 뚜껑을 약한 힘으로 같은 자리에서 재파지 (이후 바닥까지 유지)."""
            motion.publish_status(
                task, "regrasp_cap_light", "running",
                f"약파지 (force={cap_grasp_force_after_open:.0f})",
            )
            motion.gripper.grip_and_verify(
                "bottle_cap",
                force=cap_grasp_force_after_open,
                width_units=0,
                wait_sec=cap_grasp_regrasp_wait,
            )
            motion.publish_status(task, "regrasp_cap_light", "done")

        def _lift_cap() -> None:
            """개봉한 뚜껑을 베이스 Z로 수직 들어올려 병에서 분리 확보."""
            motion.move_base_z_delta(cap_lift, "lift_cap", task,
                                     vel=fast_vel, acc=fast_acc)

        def _restore_home_j6() -> None:
            """개봉으로 J6 한계까지 돈 뒤 home 조인트의 J6 각도로만 복원."""
            joints = motion.get_current_joint()
            target = list(joints)
            target[5] = _normalize_joint_angle(home_joint[5])
            motion.movej_joint(
                target, "restore_home_j6", task,
                vel=fast_jvel, acc=fast_jacc,
            )

        def _move_place_y() -> None:
            """Y축만 이동해 바닥 안착 Y로 이격 — X·Z·자세 유지."""
            cur = motion.get_current_tcp_pose()
            target = [cur[0], place_y, cur[2], cur[3], cur[4], cur[5]]
            motion.move_task_pose(target, "move_place_y", task,
                                  vel=fast_vel, acc=fast_acc)

        def _place_cap_down() -> None:
            """현재 XY에서 Z만 바닥(floor_z)보다 cap_place_extra 만큼 더 하강."""
            cur = motion.get_current_tcp_pose()
            target = [cur[0], cur[1], place_floor_z, cur[3], cur[4], cur[5]]
            motion.move_task_pose(target, "place_cap_down", task,
                                  vel=grasp_vel, acc=grasp_acc)

        def _save_cap_place_pose() -> None:
            """바닥 안착 직후 실제 TCP 포즈 저장 — close_bottle 이 동일 위치에서 집도록."""
            pose = motion.get_current_tcp_pose()
            save_cap_place_pose(pose)
            motion.publish_status(
                task, "save_cap_place_pose", "done",
                f"뚜껑 안착 위치 저장 "
                f"(x={pose[0]:.1f}, y={pose[1]:.1f}, z={pose[2]:.1f})",
            )

        def _release_cap_on_floor() -> None:
            """바닥에 내려놓은 뒤에만 그리퍼를 연다."""
            motion.gripper.open()

        def _retract_from_place() -> None:
            """뚜껑 놓은 뒤 approach 높이로 복귀 — 자세 유지."""
            cur = motion.get_current_tcp_pose()
            target = [cur[0], cur[1], floor_z + place_approach_z, cur[3], cur[4], cur[5]]
            motion.move_task_pose(target, "retract_from_place", task,
                                  vel=fast_vel, acc=fast_acc)

        def _home_finish() -> None:
            """뚜껑을 바닥에 놓은 뒤 home 으로 복귀.

            home 으로 바로 movej 하면 관절 보간으로 대각선 이동해 물통과
            충돌할 수 있으므로, 먼저 베이스 Z 로 충분히 수직 상승한 뒤 복귀한다.
            """
            motion.move_base_z_delta(lift, "home_lift", task,
                                     vel=fast_vel, acc=fast_acc)
            motion.movej_joint(home_joint, "home_finish", task,
                               vel=fast_jvel, acc=fast_jacc)

        steps = [
            ("prepare_home",        _prepare_home),
            ("approach_water_cap",  _approach_water_cap),
            ("grasp_cap",           lambda: motion.gripper.close_and_verify("bottle_cap")),
            ("carry_to_cupholder",  _carry_to_cupholder),
            ("lower_into_holder",   _lower_into_holder),
            ("release_in_holder",   motion.gripper.open),
            ("approach_for_reopen", _approach_for_reopen),
            ("descend_to_open_start", _descend_to_open_start),
            ("regrasp_close",       lambda: motion.gripper.close_and_verify("bottle_cap")),
            # --- (주석) start_joint + grasp_descent 재파지 ---
            # ("regrasp_move_start",  _regrasp_move_start),
            # ("regrasp_descend",     _regrasp_descend),
            # ("regrasp_close",       motion.gripper.close),
            ("twist_open",          _twist_open),
            ("descend_before_regrasp", _descend_before_regrasp),
            ("release_after_open",  _release_after_open),
            ("regrasp_cap_light",   _regrasp_cap_light),
            ("lift_cap",            _lift_cap),
            ("restore_home_j6",     _restore_home_j6),
            ("move_place_y",        _move_place_y),
            ("place_cap_down",      _place_cap_down),
            ("release_cap",         _release_cap_on_floor),
            ("save_cap_place_pose", _save_cap_place_pose),
            ("retract_from_place",  _retract_from_place),
            ("home_finish",         _home_finish),
        ]
        motion.run_sequence(task, steps)
