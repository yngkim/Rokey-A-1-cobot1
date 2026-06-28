"""외력 감지 후 사용자 선택 대기."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cobot1.bridge.safety_decision_gate import SafetyDecisionAction, get_safety_decision_gate
from cobot1.motion.exceptions import CobotError, SafetyViolation, TaskCancelled

if TYPE_CHECKING:
    from cobot1.motion.primitives import RobotMotion


def _cli_prompt() -> SafetyDecisionAction:
    print(
        "\n[외력 감지] 로봇 주변을 확인한 뒤 선택하세요:\n"
        "  Enter = 작업 계속\n"
        "  h = 홈 복귀\n"
        "  q = 여기서 중단\n"
    )
    try:
        line = input("선택> ").strip().lower()
    except EOFError as exc:
        raise CobotError(
            "터미널 입력을 받을 수 없습니다.",
            code="SAFETY_NO_INPUT",
            user_message="웹 UI에서 외력 대응을 선택해 주세요.",
        ) from exc
    if line in ("", "r", "resume"):
        return "resume"
    if line in ("h", "home"):
        return "home"
    if line in ("q", "a", "abort"):
        return "abort"
    return "resume"


def wait_for_safety_decision(
    motion: RobotMotion,
    task: str,
    step_name: str,
    exc: SafetyViolation,
    cfg: dict,
) -> SafetyDecisionAction:
    """외력 감지 후 resume/abort/home 선택까지 대기."""
    gate = get_safety_decision_gate()
    message = exc.user_message or str(exc)
    gate.begin_wait(task, step_name, message)
    motion.publish_status(
        task,
        "safety_pause",
        "paused",
        message,
        extra={"code": exc.code},
    )

    timeout = float(cfg.get("decision_timeout_sec", 0))

    if gate.web_sync_enabled:
        decision = gate.wait(
            timeout,
            cancelled=lambda: _is_cancelled(motion),
        )
        if decision is None:
            if _is_cancelled(motion):
                gate.clear()
                raise TaskCancelled("사용자가 작업을 취소했습니다.", code="USER_CANCEL")
            gate.clear()
            raise CobotError(
                "외력 대응 선택 시간이 초과되었습니다.",
                code="SAFETY_DECISION_TIMEOUT",
                user_message="외력 대응 선택 시간이 초과되었습니다.",
            )
    else:
        decision = _cli_prompt()

    gate.clear()
    return decision


def prepare_resume_after_external_force(
    motion: RobotMotion,
    task: str,
    step_name: str,
    cfg: dict,
) -> None:
    """재개 전 안정화 및 안전 감시 재시작."""
    settle_sec = float(cfg.get("resume_settle_sec", 1.5))
    max_norm = float(cfg.get("resume_force_max_norm", 25.0))
    motion.interruptible_sleep(settle_sec)
    norm = motion.safety.read_tool_force_norm()
    if norm > max_norm:
        motion._ctx.node.get_logger().warn(
            f"[{task}] 재개 전 외력 |τ|={norm:.1f}N (임계 {max_norm:.1f}N) — 계속 진행"
        )
    motion.safety.clear_external_force_violation()
    motion.safety.restart_monitor(task)
    motion.publish_status(
        task,
        step_name,
        "running",
        "외력 확인 후 작업 재개",
    )


def _is_cancelled(motion: RobotMotion) -> bool:
    try:
        motion._check_cancel()
        return False
    except TaskCancelled:
        return True
