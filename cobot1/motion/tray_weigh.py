"""식판 파지 상태에서 tool force Z축으로 상대 무게(식사량 %)를 측정."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from cobot1.motion.exceptions import CobotError
from cobot1.runtime_state import (
    clear_tray_weight_session,
    compute_net_intake_pct,
    get_tray_tare,
    get_tray_weight_session,
    net_food_load,
    save_tray_weight_phase,
)

if TYPE_CHECKING:
    from cobot1.motion.primitives import RobotMotion

TrayPhase = Literal["before", "after", "tare"]

_PHASE_LABEL = {"before": "식전", "after": "식후", "tare": "공차"}


@dataclass
class TrayWeightReading:
    phase: TrayPhase
    fz_n: float
    timestamp: float
    force_vector: list[float]


def _log_tray_weight(
    motion: RobotMotion,
    reading: TrayWeightReading,
    *,
    task: str,
    before_fz: float | None = None,
    intake_pct: float | None = None,
    tare_fz: float | None = None,
) -> None:
    """터미널(ROS logger)에 무게·섭취율 로그."""
    label = _PHASE_LABEL.get(reading.phase, reading.phase)
    fz_abs = abs(reading.fz_n)
    motion._ctx.node.get_logger().info(
        f"[{task}] {label} 무게 측정 완료 (들어올린 후): "
        f"Fz={reading.fz_n:.2f} N (|Fz|={fz_abs:.2f} N)"
    )
    if reading.phase == "after" and before_fz is not None and intake_pct is not None:
        resolved_tare = tare_fz if tare_fz is not None else get_tray_tare()
        if resolved_tare is not None:
            net_before = net_food_load(before_fz, resolved_tare)
            net_after = net_food_load(reading.fz_n, resolved_tare)
            motion._ctx.node.get_logger().info(
                f"[{task}] 식사량 계산: tare={abs(resolved_tare):.2f} N, "
                f"식전 net={net_before:.2f} N → 식후 net={net_after:.2f} N · "
                f"섭취율 약 {int(round(intake_pct))}%"
            )
        else:
            motion._ctx.node.get_logger().info(
                f"[{task}] 식사량 계산: 식전 |Fz|={abs(before_fz):.2f} N → "
                f"식후 |Fz|={fz_abs:.2f} N · 섭취율 약 {int(round(intake_pct))}%"
            )


def compute_intake_pct(
    before_fz: float,
    after_fz: float,
    *,
    min_load_n: float = 2.0,
    tare_fz: float | None = None,
) -> float | None:
    """식전·식후 Fz와 공차로 순 음식 무게 기준 섭취율(%) 추정."""
    return compute_net_intake_pct(
        before_fz,
        after_fz,
        tare_fz=tare_fz,
        min_load_n=min_load_n,
    )


def require_tray_tare() -> float:
    """저장된 공차 Fz. 없으면 CobotError."""
    tare = get_tray_tare()
    if tare is None:
        raise CobotError(
            "트레이/식판 공차가 보정되지 않았습니다. "
            "ros2 run cobot1 calibrate_tray_tare 를 먼저 실행하세요.",
            code="TRAY_TARE_NOT_CALIBRATED",
            user_message="트레이·식판 무게 보정이 필요합니다. 관리자에게 문의해 주세요.",
        )
    return tare


def capture_tray_weight(
    motion: RobotMotion,
    cfg: dict,
    *,
    phase: TrayPhase,
    task: str,
    at_current_pose: bool = False,
    carry_cfg: dict | None = None,
    lift_before_measure: bool = False,
    lower_after_measure: bool = False,
) -> TrayWeightReading:
    """파지 포즈 또는 weigh_joint에서 정지 후 Z축 힘 샘플.

    lift_before_measure: True면 측정 전 Z 상승(전체 하중을 그리퍼에 실은 뒤 Fz 샘플).
    lower_after_measure: True면 측정 후 Z 하강(원위치 내려놓기 전 복귀).
    """
    from cobot1.motion.tray_carry import lift_tray_for_carry, lower_tray_after_weigh

    vel = float(cfg.get("weigh_joint_vel", 10.0))
    acc = float(cfg.get("weigh_joint_acc", 10.0))
    settle_sec = float(cfg.get("settle_sec", 2.0))
    sample_count = int(cfg.get("sample_count", 12))
    sample_interval = float(cfg.get("sample_interval_sec", 0.08))

    if at_current_pose:
        if not motion.gripper.is_closed:
            raise CobotError(
                "그리퍼가 열린 상태입니다.",
                code="GRIPPER_OPEN",
                user_message="식판을 잡은 뒤 무게를 측정해 주세요.",
            )
        if lift_before_measure:
            if carry_cfg is None:
                raise CobotError(
                    "무게 측정 전 상승 설정에 carry_cfg가 필요합니다.",
                    code="TRAY_WEIGH_NO_CARRY_CFG",
                )
            lift_tray_for_carry(
                motion,
                task,
                carry_cfg,
                label=f"tray_weigh_{phase}_lift",
            )
        motion.publish_status(
            task,
            f"tray_weigh_{phase}",
            "running",
            "식판 무게 측정 (들어올린 후)" if lift_before_measure else f"식판 무게 측정 ({phase})",
        )
    else:
        weigh_joint = list(cfg["weigh_joint"])
        motion.movej_joint(
            weigh_joint,
            f"tray_weigh_{phase}",
            task,
            vel=vel,
            acc=acc,
        )
    time.sleep(settle_sec)

    baseline = motion.safety.sample_force_baseline(
        samples=sample_count,
        interval_sec=sample_interval,
    )
    fz_n = float(baseline[2])
    reading = TrayWeightReading(
        phase=phase,
        fz_n=fz_n,
        timestamp=time.time(),
        force_vector=[float(v) for v in baseline[:6]],
    )

    extra: dict[str, object] = {
        "phase": phase,
        "fz_n": round(fz_n, 3),
    }
    if phase == "after":
        session = get_tray_weight_session()
        before_fz = session.get("before_fz") if session else None
        if before_fz is not None and get_tray_tare() is not None:
            intake = compute_intake_pct(
                float(before_fz),
                fz_n,
                min_load_n=float(cfg.get("min_load_n", 2.0)),
            )
            if intake is not None:
                extra["intake_pct"] = round(intake, 1)
                tare = get_tray_tare()
                if tare is not None:
                    extra["tare_fz"] = round(tare, 3)

    motion.publish_status(
        task,
        f"tray_weigh_{phase}",
        "done",
        f"식판 무게 측정 ({phase})",
        extra=extra,
    )
    if phase == "before":
        _log_tray_weight(motion, reading, task=task)
    elif "intake_pct" in extra:
        session = get_tray_weight_session()
        before_fz = session.get("before_fz") if session else None
        if before_fz is not None:
            _log_tray_weight(
                motion,
                reading,
                task=task,
                before_fz=float(before_fz),
                intake_pct=float(extra["intake_pct"]),
                tare_fz=get_tray_tare(),
            )
        else:
            _log_tray_weight(motion, reading, task=task)
    else:
        _log_tray_weight(motion, reading, task=task)
    if lower_after_measure and carry_cfg is not None:
        lower_tray_after_weigh(
            motion,
            task,
            carry_cfg,
            label=f"tray_weigh_{phase}_lower",
        )
    return reading


def resolve_tray_phase(cfg: dict) -> TrayPhase:
    """phase_mode: auto | before | after."""
    mode = str(cfg.get("phase_mode", "auto")).strip().lower()
    if mode in ("before", "after"):
        return mode  # type: ignore[return-value]

    session = get_tray_weight_session()
    if session and session.get("before_fz") is not None and session.get("after_fz") is None:
        return "after"
    return "before"


def log_meal_weight_only(
    user_id: str,
    reading: TrayWeightReading,
    *,
    task: str,
) -> dict:
    """식전 세션 없을 때 식후 무게만 기록."""
    from cobot1.bridge.care_store import EVENT_MEAL, get_care_store

    store = get_care_store()
    if store.get_user(user_id) is None:
        store.ensure_user(user_id, user_id)

    detail = {
        "after_fz": round(reading.fz_n, 3),
        "method": "tool_force_fz",
        "task": task,
    }
    note = f"식후 무게 {abs(reading.fz_n):.1f} N"
    return store.record_event(
        user_id=user_id,
        event_type=EVENT_MEAL,
        quantity=1.0,
        unit="serving",
        note=note,
        source="robot",
        detail=detail,
    )


def record_tray_weight_reading(
    reading: TrayWeightReading,
    cfg: dict,
    *,
    task: str,
    care_user_id: str,
    allow_missing_before: bool = False,
) -> float | None:
    """세션 저장. after 단계면 섭취율 계산·케어 기록까지 수행."""
    source = task
    if reading.phase == "before":
        clear_tray_weight_session()
        save_tray_weight_phase("before", reading.fz_n, source=source)
        return None

    session = save_tray_weight_phase("after", reading.fz_n, source=source)
    before_fz = session.get("before_fz")
    if before_fz is None:
        if allow_missing_before:
            log_meal_weight_only(care_user_id, reading, task=task)
            return None
        raise CobotError(
            "식전 측정값이 없습니다. 먼저 식사 가져오기(식전 측정)를 실행하세요.",
            code="TRAY_WEIGHT_NO_BEFORE",
            user_message="식전 무게 측정이 없어 식사량을 계산할 수 없습니다.",
        )

    min_load = float(cfg.get("min_load_n", 2.0))
    tare_fz = require_tray_tare()
    intake_pct = compute_intake_pct(
        float(before_fz),
        reading.fz_n,
        min_load_n=min_load,
        tare_fz=tare_fz,
    )
    if intake_pct is None:
        net_before = net_food_load(float(before_fz), tare_fz)
        raise CobotError(
            f"순 음식 부하가 너무 작습니다 (net < {min_load} N, net={net_before:.2f} N).",
            code="TRAY_WEIGHT_TOO_LIGHT",
            user_message="식판 무게가 감지되지 않았습니다. 식판을 잡았는지 확인해 주세요.",
        )

    detail = {
        "before_fz": round(float(before_fz), 3),
        "after_fz": round(reading.fz_n, 3),
        "tare_fz": round(tare_fz, 3),
        "net_before_n": round(net_food_load(float(before_fz), tare_fz), 3),
        "net_after_n": round(net_food_load(reading.fz_n, tare_fz), 3),
        "intake_pct": round(intake_pct, 1),
        "remaining_pct": round(100.0 - intake_pct, 1),
        "method": "tool_force_fz",
        "task": task,
    }
    log_meal_intake_care(care_user_id, intake_pct, detail)
    clear_tray_weight_session()
    return intake_pct


def log_meal_intake_care(
    user_id: str,
    intake_pct: float,
    reading_detail: dict,
) -> dict:
    """케어 DB에 식사(섭취율) 이벤트 기록."""
    from cobot1.bridge.care_store import EVENT_MEAL, get_care_store

    store = get_care_store()
    if store.get_user(user_id) is None:
        store.ensure_user(user_id, user_id)

    remaining_pct = max(0.0, min(100.0, 100.0 - float(intake_pct)))
    note = f"식사량 약 {int(round(intake_pct))}% 섭취"
    detail = {
        **reading_detail,
        "intake_pct": round(float(intake_pct), 1),
        "remaining_pct": round(remaining_pct, 1),
        "method": reading_detail.get("method", "tool_force_fz"),
    }
    return store.record_event(
        user_id=user_id,
        event_type=EVENT_MEAL,
        quantity=1.0,
        unit="serving",
        note=note,
        source="robot",
        detail=detail,
    )
