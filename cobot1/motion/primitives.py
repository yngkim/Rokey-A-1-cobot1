"""재시도·안전 복귀·외력 감시·사용자 정지가 포함된 공통 모션 프리미티브."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from rclpy.node import Node
from std_msgs.msg import String

from cobot1.motion.exceptions import CobotError, MotionError, SafetyViolation, TaskCancelled
from cobot1.motion.gripper import Gripper
from cobot1.motion.safety import SafetyGuard


@dataclass
class MotionContext:
    node: Node
    motion_cfg: dict
    gripper_cfg: dict
    safety_cfg: dict | None = None
    status_topic: str = "cobot1/status"


class RobotMotion:
    def __init__(self, ctx: MotionContext):
        self._ctx = ctx
        self._node = ctx.node
        self._cfg = ctx.motion_cfg
        self._retry = int(self._cfg.get("retry_count", 1))
        self._cancel = threading.Event()
        self._status_pub = self._node.create_publisher(String, ctx.status_topic, 10)
        self._gripper = Gripper(self._node, ctx.gripper_cfg)
        safety_cfg = ctx.safety_cfg or {}
        self._safety = SafetyGuard(self._node, safety_cfg, self.publish_status)
        self._import_motion_api()

    @property
    def gripper(self) -> Gripper:
        return self._gripper

    @property
    def safety(self) -> SafetyGuard:
        return self._safety

    def shutdown(self) -> None:
        """안전 감시 등 모션 리소스를 해제합니다."""
        self._safety.shutdown()

    def clear_cancel(self) -> None:
        self._cancel.clear()

    def request_stop(self, task: str = "motion") -> None:
        """사용자 정지 — 모션 중단 요청."""
        self._cancel.set()
        self.publish_status(task, "user_stop", "stopping", "정지 요청됨")
        self._safety.request_move_stop()

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise TaskCancelled("사용자가 작업을 중단했습니다.")

    def interruptible_sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + float(seconds)
        while time.monotonic() < deadline:
            self._check_cancel()
            time.sleep(0.08)

    def _import_motion_api(self) -> None:
        from cobot1.motion.dsr_imports import import_dsr_api

        api = import_dsr_api()
        self.DR_BASE = api["DR_BASE"]
        self.DR_TOOL = api["DR_TOOL"]
        self.DR_MV_MOD_REL = api["DR_MV_MOD_REL"]
        self.movej = api["movej"]
        self.movel = api["movel"]
        self.mwait = api["mwait"]
        self.check_motion = api["check_motion"]
        self.posj = api["posj"]
        self.posx = api["posx"]
        self.trans = api["trans"]
        self._get_last_alarm = api["get_last_alarm"]

    def publish_status(
        self,
        task: str,
        step: str,
        state: str,
        message: str = "",
        extra: dict | None = None,
    ) -> None:
        payload = {
            "task": task,
            "step": step,
            "state": state,
            "message": message,
            "timestamp": time.time(),
        }
        if extra:
            payload.update(extra)
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self._status_pub.publish(msg)
        self._node.get_logger().info(f"[{task}] {step} ({state}) {message}")

    def _run_with_retry(self, label: str, action: Callable[[], None]) -> None:
        self._safety.check_or_raise()
        self._check_cancel()
        last_error: Exception | None = None
        for attempt in range(self._retry + 1):
            try:
                self._safety.check_or_raise()
                self._check_cancel()
                action()
                self.mwait(0)
                self._safety.check_or_raise()
                self._check_cancel()
                if self.check_motion() != 0:
                    raise MotionError(
                        f"{label}: 모션 완료 확인 실패",
                        code="MOTION_INCOMPLETE",
                        user_message="동작이 완료되지 않았습니다. 로봇 상태를 확인해 주세요.",
                    )
                return
            except (SafetyViolation, TaskCancelled):
                raise
            except Exception as exc:
                last_error = exc
                self._node.get_logger().warn(
                    f"{label} 실패 (시도 {attempt + 1}/{self._retry + 1}): {exc}"
                )
                time.sleep(0.3)
        raise MotionError(
            f"{label} 최종 실패: {last_error}",
            code="MOTION_FAILED",
            user_message="반복 시도 후에도 동작에 실패했습니다.",
        )

    def go_home(self, task: str = "motion") -> None:
        self.publish_status(task, "go_home", "running")
        home = self.posj(self._cfg["home_joint"])
        vel = self._cfg["joint_vel"]
        acc = self._cfg["joint_acc"]

        def _move():
            self.movej(home, vel=vel, acc=acc)

        self._run_with_retry("go_home", _move)
        self.publish_status(task, "go_home", "done")

    def move_task_pose(
        self,
        pose: Sequence[float],
        label: str,
        task: str,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
    ) -> None:
        self.publish_status(task, label, "running")
        target = self.posx(list(pose))
        v = vel or self._cfg["task_vel"]
        a = acc or self._cfg["task_acc"]

        def _move():
            self.movel(target, vel=v, acc=a, ref=self.DR_BASE)

        self._run_with_retry(label, _move)
        self.publish_status(task, label, "done")

    def move_relative_tool(
        self,
        delta: Sequence[float],
        label: str,
        task: str,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
    ) -> None:
        self.publish_status(task, label, "running")
        v = vel or self._cfg["task_vel"]
        a = acc or self._cfg["task_acc"]

        def _move():
            self.movel(
                list(delta),
                vel=v,
                acc=a,
                ref=self.DR_TOOL,
                mod=self.DR_MV_MOD_REL,
            )

        self._run_with_retry(label, _move)
        self.publish_status(task, label, "done")

    def approach_pose(
        self,
        pose: Sequence[float],
        height_mm: float,
        label: str,
        task: str,
    ) -> None:
        approach = self.trans(
            self.posx(list(pose)),
            [0.0, 0.0, float(height_mm), 0.0, 0.0, 0.0],
            self.DR_BASE,
            self.DR_BASE,
        )
        self.publish_status(task, label, "running")
        vel = self._cfg["task_vel"]
        acc = self._cfg["task_acc"]

        def _move():
            self.movel(approach, vel=vel, acc=acc, ref=self.DR_BASE)

        self._run_with_retry(label, _move)
        self.publish_status(task, label, "done")

    def retreat_z(self, height_mm: float, label: str, task: str) -> None:
        self.move_relative_tool(
            [0.0, 0.0, float(height_mm), 0.0, 0.0, 0.0],
            label,
            task,
        )

    def rotate_tool_z_steps(
        self,
        total_deg: float,
        steps: int,
        label_prefix: str,
        task: str,
        pause_sec: float = 0.15,
    ) -> None:
        if steps <= 0:
            raise MotionError("twist_steps는 1 이상이어야 합니다")
        step_angle = total_deg / steps
        for index in range(steps):
            self._check_cancel()
            self.move_relative_tool(
                [0.0, 0.0, 0.0, 0.0, 0.0, step_angle],
                f"{label_prefix}_{index + 1}",
                task,
            )
            if pause_sec > 0 and index < steps - 1:
                self.interruptible_sleep(pause_sec)

    def safe_abort(self, task: str, reason: str, code: str = "SAFE_ABORT") -> None:
        alarm = self._safety.get_last_alarm_text()
        detail = {"reason": reason}
        if alarm:
            detail["last_alarm"] = alarm
            self._node.get_logger().error(f"[{task}] 알람: {alarm}")

        self.publish_status(
            task,
            "safe_abort",
            "error",
            reason,
            extra={"code": code, "detail": detail},
        )

        try:
            self.gripper.open()
        except Exception as exc:
            self._node.get_logger().warn(f"그리퍼 열기 실패: {exc}")

        try:
            retreat = float(self._cfg.get("retreat_height_mm", 100))
            self.retreat_z(retreat, "safe_retreat", task)
            self.go_home(task)
            self.publish_status(task, "safe_abort", "recovered", "안전 복귀 완료")
        except Exception as exc:
            self.publish_status(
                task,
                "safe_abort",
                "critical",
                f"안전 복귀 실패: {exc}",
                extra={"code": "RECOVERY_FAILED"},
            )

    def run_sequence(
        self,
        task: str,
        steps: Iterable[tuple[str, Callable[[], None]]],
    ) -> None:
        self.clear_cancel()
        self._safety.start(task)
        try:
            for step_name, step_action in steps:
                self._safety.check_or_raise()
                self._check_cancel()
                try:
                    step_action()
                except TaskCancelled as exc:
                    self.publish_status(
                        task,
                        step_name,
                        "stopped",
                        exc.user_message,
                        extra={"code": exc.code},
                    )
                    self.safe_abort(task, exc.user_message, exc.code)
                    raise
                except SafetyViolation as exc:
                    self.publish_status(
                        task,
                        step_name,
                        "error",
                        exc.user_message,
                        extra={"code": exc.code},
                    )
                    self.safe_abort(task, exc.user_message, exc.code)
                    raise
                except CobotError as exc:
                    user_msg = exc.user_message or str(exc)
                    self.publish_status(
                        task,
                        step_name,
                        "error",
                        user_msg,
                        extra={"code": exc.code},
                    )
                    self.safe_abort(task, user_msg, exc.code)
                    raise
                except Exception as exc:
                    user_msg = f"예기치 않은 오류: {exc}"
                    self.publish_status(
                        task,
                        step_name,
                        "error",
                        user_msg,
                        extra={"code": "UNKNOWN_ERROR"},
                    )
                    self.safe_abort(task, user_msg, "UNKNOWN_ERROR")
                    raise MotionError(str(exc), code="UNKNOWN_ERROR", user_message=user_msg) from exc
        finally:
            self._safety.stop()
