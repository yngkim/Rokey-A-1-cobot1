"""외력 감지 후 사용자 선택(재개/중단/홈) 대기 게이트."""

from __future__ import annotations

import threading
import time
from typing import Callable, Literal

SafetyDecisionAction = Literal["resume", "abort", "home"]

_VALID_ACTIONS = frozenset({"resume", "abort", "home"})


class SafetyDecisionGate:
    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._on_change = on_change
        self._event = threading.Event()
        self._task: str | None = None
        self._step: str | None = None
        self._message: str = ""
        self._decision: SafetyDecisionAction | None = None

    def begin_wait(self, task: str, step: str, message: str) -> None:
        with self._lock:
            self._event.clear()
            self._task = task
            self._step = step
            self._message = message
            self._decision = None
        self._notify()

    def decide(self, action: str) -> tuple[bool, str]:
        if action not in _VALID_ACTIONS:
            return False, f"action은 resume, abort, home 중 하나여야 합니다: {action}"
        with self._lock:
            if self._task is None:
                return False, "외력 대기 중인 작업이 없습니다."
            if self._decision is not None:
                return False, "이미 선택되었습니다."
            self._decision = action  # type: ignore[assignment]
            self._event.set()
        self._notify()
        return True, "선택이 반영되었습니다."

    def clear(self) -> None:
        with self._lock:
            self._task = None
            self._step = None
            self._message = ""
            self._decision = None
            self._event.clear()
        self._notify()

    def snapshot(self) -> dict[str, str | bool | None]:
        with self._lock:
            pending = self._task is not None and self._decision is None
            return {
                "safety_decision_pending": pending,
                "safety_pause_task": self._task,
                "safety_pause_step": self._step,
                "safety_pause_message": self._message or None,
            }

    def wait(
        self,
        timeout_sec: float,
        *,
        poll_sec: float = 0.05,
        cancelled: Callable[[], bool] | None = None,
    ) -> SafetyDecisionAction | None:
        unlimited = float(timeout_sec) <= 0
        deadline = None if unlimited else time.time() + float(timeout_sec)
        while unlimited or time.time() < deadline:
            if cancelled and cancelled():
                return None
            if self._event.wait(timeout=poll_sec):
                with self._lock:
                    return self._decision
        return None

    @property
    def web_sync_enabled(self) -> bool:
        return self._on_change is not None

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()


_gate: SafetyDecisionGate | None = None


def set_safety_decision_gate(gate: SafetyDecisionGate | None) -> None:
    global _gate
    _gate = gate


def ensure_safety_decision_gate() -> SafetyDecisionGate:
    global _gate
    if _gate is None:
        _gate = SafetyDecisionGate()
    return _gate


def get_safety_decision_gate() -> SafetyDecisionGate:
    return ensure_safety_decision_gate()
