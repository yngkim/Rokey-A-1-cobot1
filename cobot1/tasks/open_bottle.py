"""페트병 뚜껑 열기.

흐름:
  start_joint (병 위 5cm, 그리퍼 열림)
  → 툴 +Z 방향으로 grasp_descent_mm 하강 → 파지
  → J6 회전 + 동시 상승으로 뚜껑 개봉
  → 툴 -Z 들어올리기 → home TCP 기준 X+0/Y-100 수평 이동
  → 그리퍼 원자세 복귀(개봉 회전 되돌림) → 바닥(z=237)에 뚜껑 내려놓기
  → start_joint(시작 위치)로 복귀

start_joint 티칭:
  병 뚜껑 최상단에서 5cm 위, 그리퍼 수직 하향 자세로 티칭.
"""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class OpenBottleTask(BaseTask):
    name = "open_bottle"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        start_joint = list(cfg.get("start_joint", [0.29, 1.68, 74.79, -0.04, 103.54, 10.21]))
        motion.set_recovery_joint(home_joint)

        grasp_descent    = float(cfg.get("grasp_descent_mm", 60.0))
        cap_lift         = float(cfg.get("cap_lift_mm", 30.0))
        grasp_vel        = list(cfg.get("grasp_vel", [15, 10]))   # 섬세 작업용(느림)
        grasp_acc        = list(cfg.get("grasp_acc", [30, 15]))
        floor_z          = float(cfg.get("cap_place_floor_z_mm", 237.0))
        place_approach_z = float(cfg.get("cap_place_approach_z_mm", 50.0))

        # 일반 이동(빠름) 속도 — 섬세 작업(파지/개봉/내려놓기) 외에는 이 속도 사용
        fast_vel  = list(cfg.get("fast_vel", [80, 60]))
        fast_acc  = list(cfg.get("fast_acc", [200, 150]))
        fast_jvel = float(cfg.get("fast_joint_vel", 60.0))
        fast_jacc = float(cfg.get("fast_joint_acc", 60.0))

        # 뚜껑 놓을 위치: home_joint([0,0,90,0,90,0]) TCP 기준 X+0/Y-100 (바닥)
        from cobot1.motion.dsr_imports import import_dsr_api
        home_tcp = [float(v) for v in import_dsr_api()["fkin"](home_joint)]
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

        def _grasp_cap() -> None:
            motion.move_relative_tool(
                [0.0, 0.0, grasp_descent, 0.0, 0.0, 0.0],
                "descend_to_cap", task,
                vel=grasp_vel, acc=grasp_acc,
            )
            motion.gripper.close()

        def _twist_open() -> None:
            # 개봉은 섬세 작업 → 느린 속도
            motion.rotate_tool_z_steps(
                float(cfg["twist_angle_deg"]),
                int(cfg["twist_steps"]),
                "twist",
                task,
                pause_sec=0.0,
                rise_total_mm=float(cfg.get("twist_rise_mm", 0.0)),
                vel=grasp_vel,
                acc=grasp_acc,
            )

        def _lift_cap() -> None:
            motion.move_relative_tool(
                [0.0, 0.0, -cap_lift, 0.0, 0.0, 0.0],
                "lift_cap", task,
                vel=fast_vel, acc=fast_acc,
            )

        def _approach_cap_place() -> None:
            """먼저 수평(X+0/Y-100)으로만 이동 — 현재 높이·자세 유지, 손목 회전 없음."""
            cur = motion.get_current_tcp_pose()
            target = [place_x, place_y, cur[2], cur[3], cur[4], cur[5]]
            motion.move_task_pose(target, "approach_cap_place", task,
                                  vel=fast_vel, acc=fast_acc)

        def _place_cap_down() -> None:
            """수평 이동 후 그 자리에서 Z만 바닥(floor_z)까지 수직 하강 — 자세 유지, floor_z 이하로 절대 내려가지 않음."""
            cur = motion.get_current_tcp_pose()
            target = [place_x, place_y, floor_z, cur[3], cur[4], cur[5]]
            motion.move_task_pose(target, "place_cap_down", task,
                                  vel=grasp_vel, acc=grasp_acc)

        def _unrotate_cap() -> None:
            """개봉으로 돌아간 그리퍼를 원래 자세로 되돌림 (바닥에 놓기 전)."""
            twist_angle = float(cfg["twist_angle_deg"])
            motion.move_relative_tool(
                [0.0, 0.0, 0.0, 0.0, 0.0, -twist_angle],
                "unrotate_cap", task,
                vel=fast_vel, acc=fast_acc,
            )

        def _retract_from_place() -> None:
            """뚜껑 놓은 뒤 approach 높이로 복귀 — 자세 유지."""
            cur = motion.get_current_tcp_pose()
            target = [place_x, place_y, floor_z + place_approach_z, cur[3], cur[4], cur[5]]
            motion.move_task_pose(target, "retract_from_place", task,
                                  vel=fast_vel, acc=fast_acc)

        def _return_to_start() -> None:
            """뚜껑을 놓은 뒤 태스크 시작 위치(start_joint)로 복귀."""
            motion.movej_joint(start_joint, "return_to_start", task,
                               vel=fast_jvel, acc=fast_jacc)

        steps = [
            ("prepare_start",      _prepare_start),
            ("grasp_cap",          _grasp_cap),
            ("twist_open",         _twist_open),
            ("lift_cap",           _lift_cap),
            ("approach_cap_place", _approach_cap_place),
            ("unrotate_cap",       _unrotate_cap),
            ("place_cap_down",     _place_cap_down),
            ("release_cap",        motion.gripper.open),
            ("retract_from_place", _retract_from_place),
            ("return_to_start",    _return_to_start),
        ]
        motion.run_sequence(task, steps)
