"""UI 그리퍼 버튼 인수인계 대기 게이트."""

from __future__ import annotations

import threading
import time
from typing import Callable


class UserHandoffGate:
    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._on_change = on_change
        self._expected: str | None = None
        self._prompt = ""
        self._event = threading.Event()

    def begin_wait(self, action: str, prompt: str) -> None:
        with self._lock:
            self._event.clear()
            self._expected = action
            self._prompt = prompt
        self._notify()

    def try_confirm(self, action: str) -> tuple[bool, str]:
        with self._lock:
            if self._expected != action:
                if self._expected is None:
                    return False, "확인 대기 중인 작업이 없습니다."
                return False, "지금은 다른 확인 단계입니다."
            self._event.set()
            return True, "확인되었습니다."

    def clear(self) -> None:
        with self._lock:
            self._expected = None
            self._prompt = ""
            self._event.clear()
        self._notify()

    def snapshot(self) -> dict[str, str | None]:
        with self._lock:
            return {
                "handoff_action": self._expected,
                "handoff_prompt": self._prompt or None,
            }

    def wait(
        self,
        timeout_sec: float,
        *,
        poll_sec: float = 0.05,
        cancelled: Callable[[], bool] | None = None,
    ) -> bool:
        deadline = time.time() + max(0.0, float(timeout_sec))
        while time.time() < deadline:
            if cancelled and cancelled():
                return False
            if self._event.wait(timeout=poll_sec):
                return True
        return False

    @property
    def web_sync_enabled(self) -> bool:
        return self._on_change is not None

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()


_gate: UserHandoffGate | None = None


def set_handoff_gate(gate: UserHandoffGate | None) -> None:
    global _gate
    _gate = gate


def ensure_handoff_gate() -> UserHandoffGate:
    """API 서버 없이 ros2 run 등으로 실행할 때 기본 게이트를 준비합니다."""
    global _gate
    if _gate is None:
        _gate = UserHandoffGate()
    return _gate


def get_handoff_gate() -> UserHandoffGate:
    return ensure_handoff_gate()
