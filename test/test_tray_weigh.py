"""식판 무게 측정 — 섭취율 계산 단위 테스트."""

import pytest

from cobot1.motion.tray_weigh import compute_intake_pct, require_tray_tare
from cobot1.motion.exceptions import CobotError
from cobot1.runtime_state import (
    clear_tray_tare,
    clear_tray_weight_session,
    compute_net_intake_pct,
    compute_tray_intake_from_session,
    get_tray_tare,
    get_tray_weight_session,
    net_food_load,
    save_tray_tare,
    save_tray_weight_phase,
)


@pytest.fixture(autouse=True)
def _clean_tray_state(tmp_path, monkeypatch):
    monkeypatch.setenv("COBOT1_RUNTIME_DIR", str(tmp_path))
    clear_tray_weight_session()
    clear_tray_tare()
    yield
    clear_tray_weight_session()
    clear_tray_tare()


def test_compute_intake_pct_half_consumed():
    assert compute_intake_pct(-10.0, -5.0, tare_fz=0.0) == 50.0


def test_compute_intake_pct_fully_consumed():
    assert compute_intake_pct(10.0, 0.0, tare_fz=0.0) == 100.0


def test_compute_intake_pct_nothing_consumed():
    assert compute_intake_pct(-12.0, -12.0, tare_fz=0.0) == 0.0


def test_compute_intake_pct_below_min_load():
    assert compute_intake_pct(1.0, 0.5, min_load_n=2.0, tare_fz=0.0) is None


def test_compute_intake_pct_fully_consumed_net():
    assert compute_intake_pct(10.0, 0.0, tare_fz=0.0) == 100.0


def test_compute_intake_pct_with_tare():
    # 공차 8 N, 식전 18 N(음식 10 N), 식후 13 N(음식 5 N) → 50%
    assert compute_intake_pct(-18.0, -13.0, tare_fz=-8.0) == 50.0


def test_net_food_load():
    assert net_food_load(-18.0, -8.0) == 10.0
    assert net_food_load(-7.0, -8.0) == 0.0


def test_tray_tare_save_and_load():
    save_tray_tare(-8.12, source="test")
    assert get_tray_tare() == pytest.approx(-8.12)


def test_compute_intake_pct_requires_tare_when_missing():
    assert compute_intake_pct(-18.0, -13.0) is None


def test_require_tray_tare_raises_when_missing():
    with pytest.raises(CobotError) as exc:
        require_tray_tare()
    assert exc.value.code == "TRAY_TARE_NOT_CALIBRATED"


def test_tray_weight_session_before_after():
    save_tray_tare(0.0, source="test")
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


def test_tray_weight_session_with_tare():
    save_tray_tare(-8.0, source="test")
    save_tray_weight_phase("before", -18.0)
    save_tray_weight_phase("after", -13.0)
    session = get_tray_weight_session()
    assert session is not None
    assert session["intake_pct"] == 50.0
    assert compute_net_intake_pct(-18.0, -13.0, tare_fz=-8.0) == 50.0
