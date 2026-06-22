"""케어 로봇 예외 정의."""

from __future__ import annotations


class CobotError(Exception):
    """cobot1 공통 예외."""

    def __init__(self, message: str, code: str = "UNKNOWN", user_message: str = ""):
        super().__init__(message)
        self.code = code
        self.user_message = user_message or message


class MotionError(CobotError):
    def __init__(self, message: str, code: str = "MOTION_ERROR", user_message: str = ""):
        super().__init__(message, code, user_message)


class TaskCancelled(CobotError):
    """사용자 또는 시스템이 태스크 실행을 중단함."""

    def __init__(self, message: str = "작업이 중단되었습니다.", user_message: str = ""):
        super().__init__(message, "USER_STOP", user_message or "작업이 중단되었습니다.")


class SafetyViolation(CobotError):
    """외력·안전 상태 이상으로 동작 중단."""

    def __init__(
        self,
        message: str,
        code: str = "SAFETY_ABORT",
        user_message: str = "",
        detail: dict | None = None,
    ):
        super().__init__(message, code, user_message)
        self.detail = detail or {}
