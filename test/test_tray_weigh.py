"""식판 무게 측정 — 섭취율 계산 단위 테스트."""

from cobot1.motion.tray_weigh import compute_intake_pct
from cobot1.runtime_state import (
    clear_tray_weight_session,
    compute_tray_intake_from_session,
    get_tray_weight_session,
    save_tray_weight_phase,
)


def test_compute_intake_pct_half_consumed():
    assert compute_intake_pct(-10.0, -5.0) == 50.0


def test_compute_intake_pct_fully_consumed():
    assert compute_intake_pct(10.0, 0.0) == 100.0


def test_compute_intake_pct_nothing_consumed():
    assert compute_intake_pct(-12.0, -12.0) == 0.0


def test_compute_intake_pct_below_min_load():
    assert compute_intake_pct(1.0, 0.5, min_load_n=2.0) is None


def test_compute_intake_pct_clamps_overconsumption():
    assert compute_intake_pct(10.0, -5.0) == 100.0


def test_tray_weight_session_before_after():
    clear_tray_weight_session()
    save_tray_weight_phase("before", -20.0)
    session = get_tray_weight_session()
    assert session is not None
    assert session["before_fz"] == -20.0
    assert session.get("after_fz") is None

    save_tray_weight_phase("after", -8.0)
    session = get_tray_weight_session()
    assert session["after_fz"] == -8.0
    assert session["intake_pct"] == 60.0
    assert compute_tray_intake_from_session() == 60.0
    clear_tray_weight_session()
