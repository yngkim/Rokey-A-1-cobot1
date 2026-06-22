"""케어 태스크 공통 베이스."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cobot1.motion.primitives import MotionContext, RobotMotion


@dataclass
class TaskResult:
    success: bool
    task: str
    message: str


class BaseTask:
    name = "base"

    def __init__(self, scenarios: dict[str, Any], motion: RobotMotion):
        self._scenarios = scenarios
        self._motion = motion
        self._cfg = scenarios[self.name]

    def run(self) -> TaskResult:
        self._motion.publish_status(self.name, "start", "running")
        try:
            self._execute()
        except Exception as exc:
            self._motion.publish_status(self.name, "finish", "error", str(exc))
            return TaskResult(False, self.name, str(exc))

        self._motion.publish_status(self.name, "finish", "done", "정상 완료")
        return TaskResult(True, self.name, "정상 완료")

    def _execute(self) -> None:
        raise NotImplementedError
