"""SafetyDecisionGate 단위 테스트."""

import pytest

from cobot1.bridge.safety_decision_gate import SafetyDecisionGate


@pytest.fixture
def gate():
    g = SafetyDecisionGate()
    yield g
    g.clear()


def test_decide_resume_abort_home(gate):
    gate.begin_wait("serve_meal", "carry_to_user", "외력 감지")
    snap = gate.snapshot()
    assert snap["safety_decision_pending"] is True
    assert snap["safety_pause_task"] == "serve_meal"

    ok, _ = gate.decide("resume")
    assert ok is True
    assert gate.wait(0.1) == "resume"
    assert gate.snapshot()["safety_decision_pending"] is False


def test_decide_rejects_invalid(gate):
    gate.begin_wait("serve_meal", "grasp_tray", "test")
    ok, msg = gate.decide("invalid")
    assert ok is False
    assert "resume" in msg


def test_decide_only_once(gate):
    gate.begin_wait("return_tray", "tray_weigh_after", "test")
    assert gate.decide("abort")[0] is True
    ok, msg = gate.decide("home")
    assert ok is False
    assert "이미" in msg


def test_clear_resets_pending(gate):
    gate.begin_wait("serve_meal", "step", "msg")
    gate.clear()
    snap = gate.snapshot()
    assert snap["safety_decision_pending"] is False
    assert snap["safety_pause_task"] is None
