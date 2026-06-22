"""케어 태스크 공통 베이스."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cobot1.motion.exceptions import CobotError, SafetyViolation, TaskCancelled
from cobot1.motion.primitives import MotionContext, RobotMotion


@dataclass
class TaskResult:
    success: bool
    task: str
    message: str
    code: str = "OK"
    user_message: str = ""


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
        except SafetyViolation as exc:
            return TaskResult(
                False,
                self.name,
                str(exc),
                code=exc.code,
                user_message=exc.user_message,
            )
        except TaskCancelled as exc:
            return TaskResult(
                False,
                self.name,
                str(exc),
                code=exc.code,
                user_message=exc.user_message,
            )
        except CobotError as exc:
            return TaskResult(
                False,
                self.name,
                str(exc),
                code=exc.code,
                user_message=exc.user_message or str(exc),
            )
        except Exception as exc:
            return TaskResult(
                False,
                self.name,
                str(exc),
                code="UNKNOWN_ERROR",
                user_message="예기치 않은 오류로 작업이 중단되었습니다.",
            )

        self._motion.publish_status(self.name, "finish", "done", "정상 완료")
        return TaskResult(True, self.name, "정상 완료", code="OK", user_message="작업이 완료되었습니다.")

    def _execute(self) -> None:
        raise NotImplementedError
