"""트레이 이송 — 파지 후 Z 상승 → 티칭 조인트 movej 경유."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from cobot1.motion.primitives import RobotMotion


def _carry_segment_label(idx: int, via_count: int, final_label: str) -> str:
    if idx >= via_count:
        return final_label
    return "move_route_mid" if idx == 0 else f"move_route_mid_{idx + 1}"


def lower_tray_after_weigh(
    motion: RobotMotion,
    task: str,
    cfg: dict,
    *,
    label: str = "post_weigh_lower",
) -> None:
    """무게 측정 후 Z 하강 (원위치 내려놓기 전)."""
    lift_mm = float(cfg.get("post_grasp_carry_lift_mm", 200.0))
    descend_vel = list(cfg.get("descend_vel", [12, 8]))
    descend_acc = list(cfg.get("descend_acc", [24, 16]))
    motion.move_base_z_delta(
        -lift_mm,
        label,
        task,
        vel=descend_vel,
        acc=descend_acc,
    )


def lift_tray_for_carry(
    motion: RobotMotion,
    task: str,
    cfg: dict,
    *,
    label: str = "post_grasp_lift",
) -> None:
    """TCP 자세 유지, 베이스 Z만 상승 (이송 전 장애물 회피)."""
    lift_mm = float(cfg.get("post_grasp_carry_lift_mm", 200.0))
    carry_vel = list(cfg.get("carry_vel", [20, 15]))
    carry_acc = list(cfg.get("carry_acc", [40, 30]))
    motion.retreat_base_z(
        lift_mm,
        label,
        task,
        vel=carry_vel,
        acc=carry_acc,
    )


def lift_tray_after_grasp(motion: RobotMotion, task: str, cfg: dict) -> None:
    """파지 직후 Z 상승 (begin_tray_carry 호환)."""
    lift_tray_for_carry(motion, task, cfg, label="post_grasp_lift")


def carry_tray_to_joint(
    motion: RobotMotion,
    joints: list[float],
    label: str,
    task: str,
    cfg: dict,
    *,
    via_joints: Sequence[Sequence[float]] | None = None,
) -> None:
    """티칭 조인트 movej 경유 이송 (J1~J6 보간으로 축 정렬)."""
    carry_vel = float(cfg.get("carry_joint_vel", cfg.get("approach_joint_vel", 12.0)))
    carry_acc = float(cfg.get("carry_joint_acc", cfg.get("approach_joint_acc", 12.0)))

    via = [list(j) for j in via_joints] if via_joints else []
    targets = via + [list(joints)]
    via_count = len(via)

    for idx, target_joints in enumerate(targets):
        seg_label = _carry_segment_label(idx, via_count, label)
        motion.movej_joint(
            target_joints,
            seg_label,
            task,
            vel=carry_vel,
            acc=carry_acc,
        )


def carry_tray_back_to_station(
    motion: RobotMotion,
    fkin,
    grasp_joint: list[float],
    label: str,
    task: str,
    cfg: dict,
    *,
    via_joints: Sequence[Sequence[float]] | None = None,
) -> None:
    """사용자 → 웨이포인트 → 원위치(상승 Z) → 원위치(파지) 복귀."""
    carry_vel = float(cfg.get("carry_joint_vel", cfg.get("approach_joint_vel", 12.0)))
    carry_acc = float(cfg.get("carry_joint_acc", cfg.get("approach_joint_acc", 12.0)))
    grasp_vel = float(cfg.get("grasp_joint_vel", 8.0))
    grasp_acc = float(cfg.get("grasp_joint_acc", 8.0))
    cart_vel = list(cfg.get("carry_vel", [20, 15]))
    cart_acc = list(cfg.get("carry_acc", [40, 30]))
    descend_vel = list(cfg.get("descend_vel", [12, 8]))
    descend_acc = list(cfg.get("descend_acc", [24, 16]))
    lift_mm = float(cfg.get("post_grasp_carry_lift_mm", 200.0))

    via = [list(j) for j in via_joints] if via_joints else []
    for idx, wp in enumerate(via):
        seg_label = _carry_segment_label(idx, len(via), label)
        motion.movej_joint(wp, seg_label, task, vel=carry_vel, acc=carry_acc)

    grasp_tcp = [float(v) for v in fkin(list(grasp_joint))]
    elevated_z = grasp_tcp[2] + lift_mm
    ori = grasp_tcp[3:6]

    motion.move_task_pose(
        [grasp_tcp[0], grasp_tcp[1], elevated_z, *ori],
        f"{label}_elevated",
        task,
        vel=cart_vel,
        acc=cart_acc,
    )
    motion.move_task_pose(
        [grasp_tcp[0], grasp_tcp[1], grasp_tcp[2], *ori],
        f"{label}_descend",
        task,
        vel=descend_vel,
        acc=descend_acc,
    )
    motion.movej_joint(
        list(grasp_joint),
        label,
        task,
        vel=grasp_vel,
        acc=grasp_acc,
    )


def begin_tray_carry(
    motion: RobotMotion,
    joints: list[float],
    label: str,
    task: str,
    cfg: dict,
    *,
    via_joints: Sequence[Sequence[float]] | None = None,
    skip_initial_lift: bool = False,
) -> None:
    """파지·(선택) Z 상승 → movej 경유 이송. skip_initial_lift: 무게 측정 직후 이미 상승된 경우."""
    if not skip_initial_lift:
        lift_tray_after_grasp(motion, task, cfg)
    carry_tray_to_joint(
        motion,
        joints,
        label,
        task,
        cfg,
        via_joints=via_joints,
    )
