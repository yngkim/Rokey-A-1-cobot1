"""걸레 파지 → 지정 구간 닦기 → 걸레 복귀·홈.

흐름:
  home → 걸레 파지 → 들어올림
  → 3번 접근(Z+20mm) → 3번 (하강) → 4, 5(4+8cm), 7~9 (movej, 6번 생략)
  → Z↑ 20cm → 10번 (XY→Z) → 11번 (movej)
  → Z↑ 10cm → 10번 복귀 → 걸레 든 → 걸레 파지 → 그리퍼 열기 → home

  (비활성) 1번, 2번
"""

from __future__ import annotations

from cobot1.motion.pose_utils import offset_joint_tcp_z
from cobot1.tasks.base import BaseTask


class CleanFloorTask(BaseTask):
    name = "clean_floor"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        motion.set_recovery_joint(home_joint)

        from cobot1.motion.dsr_imports import import_dsr_api

        dsr = import_dsr_api()
        z_offset = float(cfg.get("tcp_z_offset_mm", 20.0))
        _ikin_kw = {
            "fkin": dsr["fkin"],
            "ikin": dsr["ikin"],
            "get_solution_space": dsr["get_solution_space"],
        }

        def _offset_joints(joints: list[float]) -> list[float]:
            if not z_offset:
                return list(joints)
            return offset_joint_tcp_z(joints, z_offset, **_ikin_kw)

        mop_grasp_joint = list(cfg["mop_grasp_joint"])
        mop_lift_joint = list(cfg["mop_lift_joint"])
        exempt = {int(p) for p in cfg.get("wipe_z_offset_exempt", [4])}
        wipe_joints = []
        for i, j in enumerate(cfg["wipe_joints"]):
            pos = i + 1
            if pos in exempt:
                wipe_joints.append(list(j))
            else:
                wipe_joints.append(_offset_joints(list(j)))
        if len(wipe_joints) < 11:
            raise ValueError(f"clean_floor: wipe_joints must have 11 poses, got {len(wipe_joints)}")

        wipe_5_z = float(cfg.get("wipe_5_z_offset_from_4_mm", 80.0))
        if wipe_5_z:
            wipe_joints[4] = offset_joint_tcp_z(
                wipe_joints[3], wipe_5_z, **_ikin_kw,
            )

        def _wipe_joint(position: int) -> list[float]:
            """닦기 N번 위치 조인트 (1~11). wipe_joints[N-1]."""
            if not 1 <= position <= 11:
                raise ValueError(f"invalid wipe position: {position}")
            return wipe_joints[position - 1]

        transition_lift = float(cfg.get("transition_lift_mm", 200.0))
        return_prep_lift = float(cfg.get("return_prep_lift_mm", 100.0))
        lift = float(cfg.get("lift_clearance_mm", 150.0))
        wipe_3_approach_z = float(cfg.get("wipe_3_approach_z_offset_mm", 20.0))

        mop_grip_force = float(cfg.get("mop_grip_force", 120.0))
        mop_grip_settle = float(cfg.get("mop_grip_settle_sec", 3.0))

        grasp_vel = list(cfg.get("grasp_vel", [15, 10]))
        grasp_acc = list(cfg.get("grasp_acc", [30, 15]))
        carry_vel = list(cfg.get("carry_vel", [25, 20]))
        carry_acc = list(cfg.get("carry_acc", [50, 40]))
        approach_jvel = float(cfg.get("approach_joint_vel", 12.0))
        approach_jacc = float(cfg.get("approach_joint_acc", 12.0))
        wipe_jvel = float(cfg.get("wipe_joint_vel", 12.0))
        wipe_jacc = float(cfg.get("wipe_joint_acc", 12.0))
        return_jvel = float(cfg.get("return_joint_vel", approach_jvel))
        return_jacc = float(cfg.get("return_joint_acc", approach_jacc))
        return_vel = list(cfg.get("return_vel", carry_vel))
        return_acc = list(cfg.get("return_acc", carry_acc))

        def _fkin_tcp(joints: list[float]) -> list[float]:
            return [float(v) for v in dsr["fkin"](joints)]

        def _release_compliance() -> None:
            try:
                dsr["release_compliance_ctrl"]()
            except Exception:
                pass

        def _prepare_start() -> None:
            _release_compliance()
            motion.clear_cancel()
            motion.movej_joint(
                home_joint, "move_home", task,
                vel=approach_jvel, acc=approach_jacc,
            )
            motion.gripper.open()

        def _move_joint_via_xy_z(joints: list[float], label: str) -> None:
            """현재 Z 유지 → XY 수평 → 목표 Z·자세."""
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

        def _reposition_lift_xy_z(
            joints: list[float],
            label: str,
            *,
            lift_mm: float,
        ) -> None:
            motion.retreat_base_z(
                lift_mm, f"{label}_lift", task,
                vel=carry_vel, acc=carry_acc,
            )
            _move_joint_via_xy_z(joints, label)

        def _move_to_mop_grasp() -> None:
            motion.movej_joint(
                mop_grasp_joint, "move_mop_grasp", task,
                vel=approach_jvel, acc=approach_jacc,
            )

        def _grasp_mop() -> None:
            motion.publish_status(
                task, "grasp_mop", "running",
                f"걸레 파지 중 (닫힘 대기 {mop_grip_settle:.1f}초)",
            )
            motion.gripper.grip(
                force=mop_grip_force,
                width_units=0,
                wait_sec=mop_grip_settle,
            )
            motion.publish_status(
                task, "grasp_mop", "done",
                f"그리퍼 닫힘 대기 완료 ({mop_grip_settle:.1f}초)",
            )

        def _lift_mop() -> None:
            motion.movej_joint(
                mop_lift_joint, "lift_mop", task,
                vel=approach_jvel, acc=approach_jacc,
            )

        def _pause_safety_for_wipe() -> None:
            motion.pause_safety_force_abort()

        def _resume_safety_after_wipe() -> None:
            motion.resume_safety_force_abort()

        # --- 1번·2번 위치 (일시 비활성) ---
        # def _wipe_to_first() -> None: ...
        # def _wipe_to_second() -> None: ...

        def _go_to_wipe_3() -> None:
            """든 위치 → 3번 XY(현재 Z, 목표 자세) → Z+20mm → movej 3번."""
            joints = _wipe_joint(3)
            tgt = _fkin_tcp(joints)
            approach = list(tgt)
            approach[2] += wipe_3_approach_z
            cur = motion.get_current_tcp_pose()
            motion.move_task_pose(
                [tgt[0], tgt[1], cur[2], tgt[3], tgt[4], tgt[5]],
                "wipe_3_travel", task,
                vel=carry_vel, acc=carry_acc,
            )
            motion.move_task_pose(
                approach, "wipe_3_approach", task,
                vel=carry_vel, acc=carry_acc,
            )
            motion.movej_joint(
                joints, "wipe_3_descend", task,
                vel=wipe_jvel, acc=wipe_jacc,
            )

        def _wipe_segment_4_to_9() -> None:
            """4 → 5(4번 Z+8cm) → 7~9. 6번은 생략."""
            for pos in (4, 5, 7, 8, 9):
                motion.movej_joint(
                    _wipe_joint(pos), f"wipe_{pos}", task,
                    vel=wipe_jvel, acc=wipe_jacc,
                )

        def _reposition_to_tenth() -> None:
            _reposition_lift_xy_z(
                _wipe_joint(10), "wipe_10",
                lift_mm=transition_lift,
            )

        def _wipe_to_eleventh() -> None:
            motion.movej_joint(
                _wipe_joint(11), "wipe_11", task,
                vel=wipe_jvel, acc=wipe_jacc,
            )

        def _return_mop() -> None:
            """11번 → Z+10cm → 10번 → 걸레 든 → 걸레 파지."""
            motion.retreat_base_z(
                return_prep_lift, "return_prep_lift", task,
                vel=return_vel, acc=return_acc,
            )
            motion.movej_joint(
                _wipe_joint(10), "return_wipe_10", task,
                vel=return_jvel, acc=return_jacc,
            )
            motion.movej_joint(
                mop_lift_joint, "return_mop_lift", task,
                vel=approach_jvel, acc=approach_jacc,
            )
            motion.movej_joint(
                mop_grasp_joint, "return_mop_grasp", task,
                vel=approach_jvel, acc=approach_jacc,
            )

        def _release_mop() -> None:
            motion.gripper.open()

        def _go_home() -> None:
            motion.go_home(
                task,
                label="go_home",
                lift_mm=lift,
                joint_vel=return_jvel,
                joint_acc=return_jacc,
                cfg={
                    "lift_clearance_mm": lift,
                    "carry_vel": return_vel,
                    "carry_acc": return_acc,
                    "descend_vel": grasp_vel,
                    "descend_acc": grasp_acc,
                },
            )

        steps = [
            ("prepare_start", _prepare_start),
            ("move_mop_grasp", _move_to_mop_grasp),
            ("grasp_mop", _grasp_mop),
            ("lift_mop", _lift_mop),
            ("pause_safety_wipe", _pause_safety_for_wipe),
            ("go_wipe_3", _go_to_wipe_3),
            ("wipe_4_to_9", _wipe_segment_4_to_9),
            ("reposition_wipe_10", _reposition_to_tenth),
            ("wipe_11", _wipe_to_eleventh),
            ("resume_safety_wipe", _resume_safety_after_wipe),
            ("return_mop", _return_mop),
            ("release_mop", _release_mop),
            ("go_home", _go_home),
        ]
        motion.run_sequence(task, steps)
