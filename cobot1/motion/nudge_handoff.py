"""순응 제어 + tool force 폴링으로 Nudge 스타일 인수인계."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from cobot1.motion.compliance import compliance_session
from cobot1.motion.exceptions import MotionError, TaskCancelled

if TYPE_CHECKING:
    from cobot1.motion.primitives import RobotMotion


def _release_compliance() -> None:
    try:
        from cobot1.motion.dsr_imports import import_dsr_api

        import_dsr_api()["release_compliance_ctrl"]()
    except Exception:
        pass


def lift_vertical_after_grasp(
    motion: RobotMotion,
    task: str,
    label: str,
    cfg: dict,
) -> None:
    """파지 직후 XY·자세 유지, 베이스 Z만 수직 상승."""
    lift_mm = float(cfg.get("post_grasp_lift_mm", 200.0))
    carry_vel = list(cfg.get("carry_vel", [20, 15]))
    carry_acc = list(cfg.get("carry_acc", [40, 30]))
    motion.retreat_base_z(lift_mm, label, task, vel=carry_vel, acc=carry_acc)


def approach_joint_via_lift(
    motion: RobotMotion,
    joints: list[float],
    label: str,
    task: str,
    cfg: dict,
) -> None:
    """Z 상승 → XY 이동 후 movej로 티칭 조인트에 정확히 접근 (파지용).

    Cartesian 하강(movel)은 티칭 조인트와 다른 자세·도달 불가가 생길 수 있어
    상공 이동 뒤 movej로만 최종 정렬한다.
    """
    from cobot1.motion.dsr_imports import import_dsr_api

    lift_mm = float(cfg.get("lift_clearance_mm", 150.0))
    carry_vel = list(cfg.get("carry_vel", [20, 15]))
    carry_acc = list(cfg.get("carry_acc", [40, 30]))
    approach_vel = float(cfg.get("approach_joint_vel", 12.0))
    approach_acc = float(cfg.get("approach_joint_acc", 12.0))

    tcp = [float(v) for v in import_dsr_api()["fkin"](list(joints))]
    cur = motion.get_current_tcp_pose()
    travel_z = max(cur[2], tcp[2]) + lift_mm

    motion.move_vertical_to_z(
        travel_z, cur, f"{label}_lift", task, vel=carry_vel, acc=carry_acc
    )
    motion.move_task_pose(
        [tcp[0], tcp[1], travel_z, tcp[3], tcp[4], tcp[5]],
        f"{label}_travel",
        task,
        vel=carry_vel,
        acc=carry_acc,
    )
    motion.movej_joint(
        list(joints), f"{label}_align", task, vel=approach_vel, acc=approach_acc
    )


def move_joint_via_lift(
    motion: RobotMotion,
    joints: list[float],
    label: str,
    task: str,
    cfg: dict,
) -> None:
    """목표 조인트로 Z 상승 → XY 이동 → Z 하강 → 조인트 정렬 (서랍 등 장애물 회피)."""
    motion.move_joint_via_lift(joints, label, task, cfg)
    vel = float(cfg.get("approach_joint_vel", 12.0))
    acc = float(cfg.get("approach_joint_acc", 12.0))
    motion.movej_joint(list(joints), f"{label}_align", task, vel=vel, acc=acc)


def grip_phone(
    motion: RobotMotion,
    task: str,
    step: str,
    force: float,
    settle_sec: float,
) -> None:
    motion.publish_status(
        task,
        step,
        "running",
        f"핸드폰 파지 중 ({force / 10:.0f}N)",
    )
    motion.gripper.grip(
        force=force,
        width_units=0,
        wait_sec=settle_sec,
    )
    motion.publish_status(task, step, "done", "핸드폰 파지 완료")


def wait_for_external_force(
    motion: RobotMotion,
    task: str,
    step: str,
    cfg: dict,
    waiting_message: str,
) -> None:
    """compliance 활성 상태에서 외력 임계값 초과를 인수인계 신호로 대기."""
    threshold = float(cfg.get("nudge_force_threshold", 15.0))
    hold_sec = float(cfg.get("nudge_hold_sec", 0.3))
    timeout_sec = float(cfg.get("nudge_timeout_sec", 120.0))
    stiffness = [float(v) for v in cfg.get("compliance_stiffness", [80, 80, 80, 40, 40, 40])]
    ramp_sec = float(cfg.get("compliance_ramp_sec", 0.3))
    poll_sec = float(cfg.get("nudge_poll_sec", 0.05))

    motion.pause_safety_force_abort()
    motion.publish_status(task, step, "running", waiting_message)

    triggered = False
    try:
        with compliance_session(
            stiffness,
            time_sec=ramp_sec,
            node_logger=motion._node.get_logger(),
        ):
            baseline = motion.safety.sample_force_baseline(samples=6, interval_sec=0.05)
            deadline = time.monotonic() + timeout_sec
            over_since: float | None = None

            while time.monotonic() < deadline:
                motion._check_cancel()
                metric = motion.safety.contact_force_metric(
                    baseline,
                    z_only=False,
                    use_delta=True,
                )
                if metric >= threshold:
                    if over_since is None:
                        over_since = time.monotonic()
                    elif time.monotonic() - over_since >= hold_sec:
                        triggered = True
                        break
                else:
                    over_since = None
                time.sleep(poll_sec)

        if not triggered:
            raise MotionError(
                "인수인계 대기 시간 초과",
                code="HANDOFF_TIMEOUT",
                user_message="핸드폰 인수인계 시간이 초과되었습니다.",
            )
        motion.publish_status(task, step, "done", "외력 감지 — 인수인계")
    except TaskCancelled:
        raise
    finally:
        _release_compliance()
        motion.resume_safety_force_abort()
