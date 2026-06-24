"""페트병 뚜껑 닫기 (open_bottle 의 역순).

전제:
  open_bottle 이 끝나 병 뚜껑이 바닥(home TCP 기준 X+0/Y-100, z=floor_z)에
  놓여 있고, 로봇은 start_joint 에 있다고 가정한다.

흐름 (open_bottle 역순):
  start_joint (그리퍼 열림)
  → home TCP 기준 X+0/Y-100 수평 이동 → 바닥으로 하강 → 뚜껑을 '약하게' 파지
    (세게 잡으면 뚜껑이 타원으로 변형돼 병 입구와 안 맞으므로 원형 유지)
  → Z 먼저 상승 → 병 위로 수평(Y) 이동
  → 조임 반대로 미리 회전(prerotate)
  → 병 나사산 시작 지점까지 하강 → 회전(조임 방향) + 동시 하강으로 닫기
    (외력으로 정지되지 않도록 open_bottle 보다 회전 스텝을 2 줄여 살짝 덜 조임)
  → 그리퍼 열기 → 툴 -Z 상승 → start_joint 복귀

속도: 섬세 작업(바닥 파지/들어올리기/병 접근·닫기) 외에는 빠른 속도로 이동.
"""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class CloseBottleTask(BaseTask):
    name = "close_bottle"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        start_joint = list(cfg.get("start_joint", [0.29, 1.68, 74.79, -0.04, 103.54, 10.21]))
        motion.set_recovery_joint(home_joint)

        grasp_descent    = float(cfg.get("grasp_descent_mm", 60.0))
        grasp_vel        = list(cfg.get("grasp_vel", [15, 10]))   # 섬세 작업용(느림)
        grasp_acc        = list(cfg.get("grasp_acc", [30, 15]))
        floor_z          = float(cfg.get("cap_place_floor_z_mm", 237.0))
        floor_pick_extra = float(cfg.get("floor_pick_extra_mm", 5.0))
        twist_angle      = float(cfg["twist_angle_deg"])
        twist_steps      = int(cfg["twist_steps"])
        twist_rise       = float(cfg.get("twist_rise_mm", 0.0))
        grip_force       = float(cfg.get("grip_force", 100.0))    # 약파지 힘(뚜껑 변형 방지)

        # 일반 이동(빠름) 속도 — 섬세 작업 외에는 이 속도 사용
        fast_vel  = list(cfg.get("fast_vel", [80, 60]))
        fast_acc  = list(cfg.get("fast_acc", [200, 150]))
        fast_jvel = float(cfg.get("fast_joint_vel", 60.0))
        fast_jacc = float(cfg.get("fast_joint_acc", 60.0))

        # 닫기 회전: open_bottle 보다 2 스텝 줄여 덜 조임 (외력 정지 방지)
        step_angle  = twist_angle / twist_steps if twist_steps else 0.0
        close_steps = max(1, twist_steps - 2)
        close_angle = -step_angle * close_steps           # 조임 방향(개봉 반대)
        close_rise  = (twist_rise / twist_steps * close_steps) if twist_steps else 0.0

        # 뚜껑이 놓여 있는 위치: home_joint TCP 기준 X+0/Y-100 (open_bottle 과 동일)
        # 병 위 TCP(start_joint)는 Z 먼저 상승 후 수평 이동에 사용
        from cobot1.motion.dsr_imports import import_dsr_api
        api = import_dsr_api()
        home_tcp = [float(v) for v in api["fkin"](home_joint)]
        start_tcp = [float(v) for v in api["fkin"](start_joint)]
        place_x = home_tcp[0] + 0.0
        place_y = home_tcp[1] - 100.0

        def _release_compliance() -> None:
            try:
                from cobot1.motion.dsr_imports import import_dsr_api
                import_dsr_api()["release_compliance_ctrl"]()
            except Exception:
                pass

        def _prepare_start() -> None:
            _release_compliance()
            motion.clear_cancel()
            motion.movej_joint(start_joint, "move_start_joint", task,
                               vel=fast_jvel, acc=fast_jacc)
            motion.gripper.open()

        def _approach_floor_cap() -> None:
            """바닥 뚜껑 위로 수평 이동 — 현재 높이·자세 유지 (빠름)."""
            cur = motion.get_current_tcp_pose()
            target = [place_x, place_y, cur[2], cur[3], cur[4], cur[5]]
            motion.move_task_pose(target, "approach_floor_cap", task,
                                  vel=fast_vel, acc=fast_acc)

        def _descend_to_floor_cap() -> None:
            """뚜껑 높이보다 floor_pick_extra(0.5cm) 더 내려 파지 위치로 (느림/섬세)."""
            cur = motion.get_current_tcp_pose()
            target = [place_x, place_y, floor_z - floor_pick_extra, cur[3], cur[4], cur[5]]
            motion.move_task_pose(target, "descend_to_floor_cap", task,
                                  vel=grasp_vel, acc=grasp_acc)

        def _grasp_cap_gently() -> None:
            """뚜껑을 약하게 파지 — 타원 변형 방지(최대한 원형 유지)."""
            motion.gripper.grip(force=grip_force)

        def _raise_above_floor() -> None:
            """뚜껑 파지 후 Z 먼저 상승(병 위 높이까지) — 느림/섬세."""
            cur = motion.get_current_tcp_pose()
            target = [place_x, place_y, start_tcp[2], cur[3], cur[4], cur[5]]
            motion.move_task_pose(target, "raise_above_floor", task,
                                  vel=grasp_vel, acc=grasp_acc)

        def _move_over_bottle() -> None:
            """그 다음 수평(Y)으로 병 위까지 이동 — 자세 유지 (빠름)."""
            cur = motion.get_current_tcp_pose()
            target = [start_tcp[0], start_tcp[1], start_tcp[2], cur[3], cur[4], cur[5]]
            motion.move_task_pose(target, "move_over_bottle", task,
                                  vel=fast_vel, acc=fast_acc)

        def _prerotate_cap() -> None:
            """조임 회전이 끝났을 때 원자세가 되도록 조임 반대 방향으로 미리 회전 (빠름)."""
            motion.move_relative_tool(
                [0.0, 0.0, 0.0, 0.0, 0.0, -close_angle],
                "prerotate_cap", task,
                vel=fast_vel, acc=fast_acc,
            )

        def _lower_to_thread() -> None:
            """병 나사산 시작 지점(seat 위 twist_rise)까지 하강 — 느림/섬세."""
            motion.move_relative_tool(
                [0.0, 0.0, grasp_descent - twist_rise, 0.0, 0.0, 0.0],
                "lower_to_thread", task,
                vel=grasp_vel, acc=grasp_acc,
            )

        def _screw_close() -> None:
            """회전(조임 방향) + 동시 하강으로 뚜껑 닫기 — 느림/섬세, open 보다 2스텝 적게."""
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

        def _lift_off() -> None:
            """뚜껑을 놓은 뒤 툴 -Z 로 빠짐 (빠름)."""
            motion.move_relative_tool(
                [0.0, 0.0, -grasp_descent, 0.0, 0.0, 0.0],
                "lift_off", task,
                vel=fast_vel, acc=fast_acc,
            )

        def _return_to_start() -> None:
            """태스크 시작 위치(start_joint)로 복귀 (빠름)."""
            motion.movej_joint(start_joint, "return_to_start", task,
                               vel=fast_jvel, acc=fast_jacc)

        steps = [
            ("prepare_start",        _prepare_start),
            ("approach_floor_cap",   _approach_floor_cap),
            ("descend_to_floor_cap", _descend_to_floor_cap),
            ("grasp_cap",            _grasp_cap_gently),
            ("raise_above_floor",    _raise_above_floor),
            ("move_over_bottle",     _move_over_bottle),
            ("prerotate_cap",        _prerotate_cap),
            ("lower_to_thread",      _lower_to_thread),
            ("screw_close",          _screw_close),
            ("release_cap",          motion.gripper.open),
            ("lift_off",             _lift_off),
            ("return_to_start",      _return_to_start),
        ]
        motion.run_sequence(task, steps)
