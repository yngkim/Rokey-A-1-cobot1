"""식판 파지 상태에서 tool force Z축으로 상대 무게(식사량 %)를 측정."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from cobot1.motion.exceptions import CobotError
from cobot1.runtime_state import (
    clear_tray_weight_session,
    get_tray_weight_session,
    save_tray_weight_phase,
)

if TYPE_CHECKING:
    from cobot1.motion.primitives import RobotMotion

TrayPhase = Literal["before", "after"]


@dataclass
class TrayWeightReading:
    phase: TrayPhase
    fz_n: float
    timestamp: float
    force_vector: list[float]


def compute_intake_pct(
    before_fz: float,
    after_fz: float,
    *,
    min_load_n: float = 2.0,
) -> float | None:
    """식전·식후 Fz로 섭취율(%) 추정. 부호와 무관하게 절대값 기준."""
    before_abs = abs(float(before_fz))
    if before_abs < float(min_load_n):
        return None
    after_abs = abs(float(after_fz))
    pct = (before_abs - after_abs) / before_abs * 100.0
    return max(0.0, min(100.0, pct))


def capture_tray_weight(
    motion: RobotMotion,
    cfg: dict,
    *,
    phase: TrayPhase,
    task: str,
) -> TrayWeightReading:
    """고정 weigh_joint에서 정지 후 Z축 힘 샘플."""
    weigh_joint = list(cfg["weigh_joint"])
    vel = float(cfg.get("weigh_joint_vel", 10.0))
    acc = float(cfg.get("weigh_joint_acc", 10.0))
    settle_sec = float(cfg.get("settle_sec", 2.0))
    sample_count = int(cfg.get("sample_count", 12))
    sample_interval = float(cfg.get("sample_interval_sec", 0.08))

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
        if before_fz is not None:
            intake = compute_intake_pct(
                float(before_fz),
                fz_n,
                min_load_n=float(cfg.get("min_load_n", 2.0)),
            )
            if intake is not None:
                extra["intake_pct"] = round(intake, 1)

    motion.publish_status(
        task,
        f"tray_weigh_{phase}",
        "done",
        f"식판 무게 측정 ({phase})",
        extra=extra,
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


def record_tray_weight_reading(
    reading: TrayWeightReading,
    cfg: dict,
    *,
    task: str,
    care_user_id: str,
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
        raise CobotError(
            "식전 측정값이 없습니다. 먼저 식전(before) 측정을 실행하세요.",
            code="TRAY_WEIGHT_NO_BEFORE",
            user_message="식전 무게 측정이 없어 식사량을 계산할 수 없습니다.",
        )

    min_load = float(cfg.get("min_load_n", 2.0))
    intake_pct = compute_intake_pct(
        float(before_fz),
        reading.fz_n,
        min_load_n=min_load,
    )
    if intake_pct is None:
        raise CobotError(
            f"식전 부하가 너무 작습니다 (|Fz| < {min_load} N).",
            code="TRAY_WEIGHT_TOO_LIGHT",
            user_message="식판 무게가 감지되지 않았습니다. 식판을 잡았는지 확인해 주세요.",
        )

    detail = {
        "before_fz": round(float(before_fz), 3),
        "after_fz": round(reading.fz_n, 3),
        "intake_pct": round(intake_pct, 1),
        "remaining_pct": round(100.0 - intake_pct, 1),
        "method": "tool_force_fz",
        "task": task,
    }
    log_meal_intake_care(care_user_id, intake_pct, detail)
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
