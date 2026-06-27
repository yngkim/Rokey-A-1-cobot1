"""UI 확인 버튼으로 트레이 인수인계."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from cobot1.bridge.handoff_gate import get_handoff_gate
from cobot1.motion.exceptions import CobotError, TaskCancelled

if TYPE_CHECKING:
    from cobot1.motion.primitives import RobotMotion

ConfirmAction = Literal["tray_return"]

_PROMPTS = {
    "tray_return": "트레이 사용이 끝나면 「트레이 가져가기」 버튼을 눌러 주세요",
}


def _is_cancelled(motion: RobotMotion) -> bool:
    try:
        motion._check_cancel()
        return False
    except TaskCancelled:
        return True


def _wait_cli_confirm(
    motion: RobotMotion,
    gate,
    action: ConfirmAction,
    prompt: str,
) -> None:
    """웹 UI 없이 ros2 run 등 단독 실행 시 터미널 Enter로 확인."""
    motion._ctx.node.get_logger().info(
        f"{prompt} (터미널에서 Enter → [트레이 가져가기])"
    )
    try:
        input()
    except EOFError as exc:
        raise CobotError(
            "터미널 입력을 받을 수 없습니다.",
            code="HANDOFF_NO_INPUT",
            user_message="웹 UI에서 실행하거나 대화형 터미널에서 Enter를 눌러 주세요.",
        ) from exc
    ok, message = gate.try_confirm(action)
    if not ok:
        raise CobotError(
            message,
            code="HANDOFF_CONFIRM_FAILED",
            user_message=message,
        )


def wait_for_user_confirm(
    motion: RobotMotion,
    action: ConfirmAction,
    task: str,
    cfg: dict,
) -> None:
    """UI 확인 버튼 대기 (그리퍼 조작 없음)."""
    gate = get_handoff_gate()
    timeout = float(cfg.get("handoff_gripper_timeout_sec", 300.0))
    prompt = str(cfg.get(f"handoff_prompt_{action}", _PROMPTS[action]))
    step = f"wait_user_confirm_{action}"

    motion.publish_status(task, step, "running", prompt)
    gate.begin_wait(action, prompt)

    try:
        if gate.web_sync_enabled:
            if not gate.wait(timeout, cancelled=lambda: _is_cancelled(motion)):
                if _is_cancelled(motion):
                    raise TaskCancelled("사용자가 작업을 취소했습니다.", code="USER_CANCEL")
                raise CobotError(
                    f"사용자 확인 대기 시간 초과 ({timeout:.0f}초)",
                    code="HANDOFF_TIMEOUT",
                    user_message="버튼 입력 시간이 초과되었습니다.",
                )
        else:
            if _is_cancelled(motion):
                raise TaskCancelled("사용자가 작업을 취소했습니다.", code="USER_CANCEL")
            _wait_cli_confirm(motion, gate, action, prompt)
        motion.publish_status(task, step, "done", prompt)
    finally:
        gate.clear()


def release_tray_at_station(motion: RobotMotion, task: str) -> None:
    """원위치에서 트레이 홀더를 내려놓습니다."""
    motion.publish_status(task, "release_tray", "running", "트레이 내려놓는 중")
    motion.gripper.open()
    motion.publish_status(task, "release_tray", "done", "트레이 내려놓기 완료")
