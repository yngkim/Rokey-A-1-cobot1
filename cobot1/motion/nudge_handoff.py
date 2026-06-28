"""순응 제어 + TCP X/Y/Z축 힘 감지로 Nudge 스타일 인수인계."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from cobot1.motion.compliance import compliance_session
from cobot1.motion.exceptions import MotionError, TaskCancelled

if TYPE_CHECKING:
    from cobot1.motion.primitives import RobotMotion


def _release_force_control() -> None:
    try:
        from cobot1.motion.dsr_imports import import_dsr_api

        api = import_dsr_api()
        api["release_force"]()
        api["release_compliance_ctrl"]()
    except Exception:
        pass


def _measure_tool_axis_magnitude(api: dict, axis: int, ref: int) -> float:
    """check_force_condition 이진 탐색으로 TCP 축 |F| 추정 (N)."""
    cond_none = api["DR_COND_NONE"]
    if api["check_force_condition"](axis, min=0.1, max=cond_none, ref=ref) != 0:
        return 0.0
    lo, hi = 0.1, 150.0
    for _ in range(12):
        mid = (lo + hi) / 2.0
        if api["check_force_condition"](axis, min=mid, max=cond_none, ref=ref) == 0:
            lo = mid
        else:
            hi = mid
    return lo


def _nudge_axes(api: dict) -> tuple[tuple[str, int], ...]:
    return (
        ("X", api["DR_AXIS_X"]),
        ("Y", api["DR_AXIS_Y"]),
        ("Z", api["DR_AXIS_Z"]),
    )


def _sample_tool_axes_baseline(
    api: dict,
    ref: int,
    *,
    samples: int,
    interval_sec: float,
) -> dict[str, float]:
    count = max(1, int(samples))
    totals = {label: 0.0 for label, _ in _nudge_axes(api)}
    for _ in range(count):
        for label, axis in _nudge_axes(api):
            totals[label] += _measure_tool_axis_magnitude(api, axis, ref)
        time.sleep(interval_sec)
    return {label: totals[label] / count for label in totals}


def _nudge_force_triggered(
    api: dict,
    ref: int,
    baselines: dict[str, float],
    force_delta: float,
) -> tuple[bool, str]:
    for label, axis in _nudge_axes(api):
        current = _measure_tool_axis_magnitude(api, axis, ref)
        trigger = baselines[label] + force_delta
        if current >= trigger:
            return True, (
                f"ΔF{label}_tool {current:.1f}N >= "
                f"baseline {baselines[label]:.1f}+{force_delta:.1f}N"
            )
    return False, ""


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
    motion.gripper.grip_and_verify(
        "phone",
        force=force,
        width_units=0,
        wait_sec=settle_sec,
    )
    motion.publish_status(task, step, "done", "핸드폰 파지 완료")


def confirm_phone_grasped(
    motion: RobotMotion,
    task: str,
    step: str,
) -> None:
    """그리퍼 닫힘 확인 후 터미널에 파지 완료를 기록한다."""
    motion.publish_status(task, step, "running", "핸드폰 파지 확인 중")
    if not motion.gripper.is_closed:
        raise MotionError(
            "그리퍼가 닫히지 않았습니다",
            code="GRIPPER_NOT_CLOSED",
            user_message="핸드폰을 잡지 못했습니다. 그리퍼 상태를 확인해 주세요.",
        )
    msg = "핸드폰을 가져왔습니다"
    motion._node.get_logger().info(f"[{task}] {msg}")
    motion.publish_status(task, step, "done", msg)


def wait_for_external_force(
    motion: RobotMotion,
    task: str,
    step: str,
    cfg: dict,
    waiting_message: str,
    *,
    auto_release_sec: float | None = None,
    timeout_sec: float | None = None,
) -> None:
    """TCP X/Y/Z축 순응 제어 + baseline 대비 ΔF 로 인수인계 외력 대기.

    auto_release_sec: 설정 시 해당 시간 경과 후 외력 없어도 자동 진행.
    timeout_sec: None이면 cfg의 nudge_timeout_sec 사용, 0 이하면 시간 제한 없음.
    """
    from cobot1.motion.dsr_imports import import_dsr_api

    api = import_dsr_api()
    force_delta = float(cfg.get("nudge_force_delta", 8.0))
    hold_sec = float(cfg.get("nudge_hold_sec", 0.4))
    if timeout_sec is None:
        configured_timeout = float(cfg.get("nudge_timeout_sec", 120.0))
    else:
        configured_timeout = float(timeout_sec)
    unlimited = configured_timeout <= 0
    settle_sec = float(cfg.get("nudge_settle_sec", 1.0))
    stiffness = [
        float(v)
        for v in cfg.get(
            "handoff_compliance_stiffness",
            cfg.get("compliance_stiffness", [800, 800, 40, 60, 60, 60]),
        )
    ]
    ramp_sec = float(cfg.get("compliance_ramp_sec", 0.5))
    poll_sec = float(cfg.get("nudge_poll_sec", 0.05))
    compliance_ref = int(cfg.get("handoff_compliance_ref", api["DR_TOOL"]))
    baseline_samples = int(cfg.get("nudge_baseline_samples", 18))
    baseline_interval = float(cfg.get("nudge_baseline_interval_sec", 0.08))

    motion.pause_safety_force_abort()
    motion.publish_status(task, step, "running", waiting_message)
    logger = motion._node.get_logger()

    triggered = False
    auto_released = False
    trigger_reason = ""
    try:
        with compliance_session(
            stiffness,
            time_sec=ramp_sec,
            node_logger=logger,
            ref=compliance_ref,
        ):
            time.sleep(ramp_sec + settle_sec)
            baselines = _sample_tool_axes_baseline(
                api,
                compliance_ref,
                samples=baseline_samples,
                interval_sec=baseline_interval,
            )
            baseline_log = ", ".join(
                f"|F{label}|={value:.1f}N" for label, value in baselines.items()
            )
            logger.info(
                f"[{task}] Nudge baseline ({baseline_log}), "
                f"delta={force_delta:.1f}N, hold={hold_sec:.1f}s"
                + (", unlimited wait" if unlimited else "")
            )

            started = time.monotonic()
            deadline = None if unlimited else started + configured_timeout
            auto_deadline = (
                started + float(auto_release_sec)
                if auto_release_sec is not None and auto_release_sec > 0
                else None
            )
            over_since: float | None = None

            while unlimited or time.monotonic() < deadline:
                motion._check_cancel()
                if auto_deadline is not None and time.monotonic() >= auto_deadline:
                    auto_released = True
                    break

                hit, reason = _nudge_force_triggered(
                    api, compliance_ref, baselines, force_delta
                )
                if hit:
                    if over_since is None:
                        over_since = time.monotonic()
                        trigger_reason = reason
                    elif time.monotonic() - over_since >= hold_sec:
                        triggered = True
                        break
                else:
                    over_since = None
                    trigger_reason = ""
                time.sleep(poll_sec)

        if auto_released:
            msg = f"인계 대기 {auto_release_sec:.0f}초 경과 — 자동 진행"
            logger.info(f"[{task}] {msg}")
            motion.publish_status(task, step, "done", msg)
        elif triggered:
            logger.info(f"[{task}] 외력 감지 — 인수인계 ({trigger_reason})")
            motion.publish_status(task, step, "done", "외력 감지 — 인수인계")
        else:
            raise MotionError(
                "인수인계 대기 시간 초과",
                code="HANDOFF_TIMEOUT",
                user_message="핸드폰 인수인계 시간이 초과되었습니다.",
            )
    except TaskCancelled:
        raise
    finally:
        _release_force_control()
        motion.resume_safety_force_abort()
