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
        self._recovery_joint: list[float] | None = None
        self._import_motion_api()

    @property
    def gripper(self) -> Gripper:
        return self._gripper

    @property
    def safety(self) -> SafetyGuard:
        return self._safety

    def shutdown(self) -> None:
        """안전 감시 등 모션 리소스를 해제합니다."""
        self._gripper.shutdown()
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

    def get_current_tcp_pose(self) -> list[float]:
        """현재 TCP pose [x,y,z,rx,ry,rz] (DR_BASE, mm/deg)."""
        from cobot1.motion.dsr_imports import import_dsr_api

        api = import_dsr_api()
        pos, _sol = api["get_current_posx"](ref=self.DR_BASE)
        if pos is None or pos == 0:
            raise MotionError(
                "TCP 위치를 읽을 수 없습니다.",
                code="POSE_READ_FAILED",
                user_message="로봇 좌표 조회에 실패했습니다.",
            )
        raw = list(pos)[:6]
        return [float(v) for v in raw]

    def move_tcp_to_z(
        self,
        z_mm: float,
        label: str,
        task: str,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
    ) -> None:
        pose = self.get_current_tcp_pose()
        pose[2] = float(z_mm)
        self.move_task_pose(pose, label, task, vel=vel, acc=acc)

    def move_base_z_delta(
        self,
        dz_mm: float,
        label: str,
        task: str,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
    ) -> None:
        """베이스 좌표계 Z만 이동 (수직 하강/상승, 자세 유지)."""
        pose = self.get_current_tcp_pose()
        pose[2] += float(dz_mm)
        self.move_task_pose(pose, label, task, vel=vel, acc=acc)

    def retreat_base_z(
        self,
        height_mm: float,
        label: str,
        task: str,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
    ) -> None:
        """베이스 Z+ 방향으로 수직 상승."""
        self.move_base_z_delta(float(height_mm), label, task, vel=vel, acc=acc)

    def move_vertical_to_z(
        self,
        z_mm: float,
        anchor: Sequence[float],
        label: str,
        task: str,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
    ) -> None:
        """anchor의 XY·자세(RxRyRz) 고정, 베이스 Z만 이동."""
        target = [
            float(anchor[0]),
            float(anchor[1]),
            float(z_mm),
            float(anchor[3]),
            float(anchor[4]),
            float(anchor[5]),
        ]
        self.move_task_pose(target, label, task, vel=vel, acc=acc)

    def approach_from_above(
        self,
        target: Sequence[float],
        label: str,
        task: str,
        lift_mm: float,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
        descend_vel: Sequence[float] | None = None,
        descend_acc: Sequence[float] | None = None,
    ) -> None:
        """빈 그리퍼로 target(파지 포즈) 위에서 수직 하강 접근.

        target 자세(rx,ry,rz)를 유지한 채, 충분히 높은 지점으로 이동 후
        베이스 Z만 수직 하강 → 옆 물체와 대각선 충돌 방지.
        """
        tgt = [float(v) for v in target[:6]]
        cur = self.get_current_tcp_pose()
        travel_z = max(cur[2], tgt[2]) + float(lift_mm)
        above = [tgt[0], tgt[1], travel_z, tgt[3], tgt[4], tgt[5]]
        self.move_task_pose(above, f"{label}_above", task, vel=vel, acc=acc)
        self.move_task_pose(tgt, f"{label}_descend", task,
                            vel=descend_vel or vel, acc=descend_acc or acc)

    def carry_to_pose(
        self,
        target: Sequence[float],
        label: str,
        task: str,
        lift_mm: float,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
        lower_vel: Sequence[float] | None = None,
        lower_acc: Sequence[float] | None = None,
        keep_orientation: bool = True,
    ) -> None:
        """물건을 든 채 target 위치로 이송: 베이스 Z 상승 → XY 수평 → 베이스 Z 하강.

        이송 중 자세를 고정(keep_orientation=True 시 현재 자세 유지)해 내용물을
        흘리지 않는다. lift_mm 만큼 두 위치 중 높은 곳보다 더 올려 수평 이동한다.
        """
        tgt = [float(v) for v in target[:6]]
        cur = self.get_current_tcp_pose()
        ori = cur[3:6] if keep_orientation else tgt[3:6]
        travel_z = max(cur[2], tgt[2]) + float(lift_mm)
        self.move_task_pose([cur[0], cur[1], travel_z, *ori],
                            f"{label}_lift", task, vel=vel, acc=acc)
        self.move_task_pose([tgt[0], tgt[1], travel_z, *ori],
                            f"{label}_travel", task, vel=vel, acc=acc)
        self.move_task_pose([tgt[0], tgt[1], tgt[2], *ori],
                            f"{label}_lower", task,
                            vel=lower_vel or vel, acc=lower_acc or acc)

    def probe_down_until_contact(
        self,
        task: str,
        anchor: Sequence[float],
        baseline_vector: Sequence[float],
        force_threshold_z: float,
        max_travel_mm: float,
        step_mm: float = 0.5,
        coarse_step_mm: float = 2.0,
        coarse_travel_mm: float = 60.0,
        max_force_z: float = 28.0,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
        fine_vel: Sequence[float] | None = None,
        fine_acc: Sequence[float] | None = None,
    ) -> tuple[float, float]:
        """anchor XY·자세 고정, 베이스 Z만 하강. Z축 힘 증가 시 즉시 정지.

        baseline_vector: 그리퍼 닫은 직후(공중) 평균 힘 — 접촉 시 ΔFz로 판정.
        Returns: (접촉 Z mm, 접촉 시 ΔFz)
        """
        if max_travel_mm <= 0 or step_mm <= 0:
            raise MotionError("max_travel_mm / step_mm 값이 올바르지 않습니다.")

        move_vel = list(vel or [15, 10])
        move_acc = list(acc or [30, 15])
        slow_vel = list(fine_vel or [8, 5])
        slow_acc = list(fine_acc or [16, 8])
        threshold = float(force_threshold_z)
        crush_limit = float(max_force_z)
        baseline = [float(v) for v in baseline_vector[:6]]
        locked = [float(v) for v in anchor[:6]]

        self.publish_status(
            task,
            "probe_down",
            "running",
            f"수직 Z- 하강 (ΔFz≥{threshold:.1f}, step≤{step_mm}mm)",
        )

        def _fz_delta() -> float:
            return self._safety.contact_force_metric(
                baseline, z_only=True, use_delta=True
            )

        def _finish(travelled: float, reason: str) -> tuple[float, float]:
            self._safety.request_move_stop()
            time.sleep(0.08)
            touch_fz = _fz_delta()
            # 순응 모드에서 명령 위치(commanded_Z)는 실제 cap 표면보다 아래일 수 있다.
            # 실제 TCP 위치를 읽어야 올바른 파지 Z를 계산할 수 있다.
            try:
                actual_pose = self.get_current_tcp_pose()
                touch_z = actual_pose[2]
            except Exception:
                touch_z = locked[2] - travelled  # fallback: commanded position
            if travelled > 0:
                backoff_mm = min(1.5, float(step_mm))
                safe_z = touch_z + backoff_mm
                self.move_vertical_to_z(
                    safe_z,
                    locked,
                    "contact_backoff",
                    task,
                    vel=slow_vel,
                    acc=slow_acc,
                )
            self.publish_status(
                task,
                "probe_down",
                "done",
                f"뚜껑 접촉 Z={touch_z:.1f}mm (ΔFz={touch_fz:.1f}, {reason})",
                extra={
                    "contact_z_mm": touch_z,
                    "touch_force_z": touch_fz,
                    "contact_reason": reason,
                },
            )
            return touch_z, touch_fz

        travelled = 0.0
        while travelled < max_travel_mm:
            self._check_cancel()
            fz = _fz_delta()
            if fz >= crush_limit:
                return _finish(travelled, "max_force")
            if fz >= threshold:
                return _finish(travelled, "contact")

            near_contact = fz >= threshold * 0.4
            if near_contact or travelled >= coarse_travel_mm:
                step = min(float(step_mm), max_travel_mm - travelled)
                v, a = slow_vel, slow_acc
            else:
                step = min(float(coarse_step_mm), max_travel_mm - travelled)
                v, a = move_vel, move_acc

            next_z = locked[2] - travelled - step
            self.move_vertical_to_z(
                next_z,
                locked,
                f"probe_z_{int(travelled)}",
                task,
                vel=v,
                acc=a,
            )
            travelled += step

            fz = _fz_delta()
            if fz >= crush_limit:
                return _finish(travelled, "max_force")
            if fz >= threshold:
                return _finish(travelled, "contact")

        raise MotionError(
            f"뚜껑 접촉 미감지 (하강 {travelled:.0f}mm)",
            code="CONTACT_NOT_FOUND",
            user_message="뚜껑 높이를 찾지 못했습니다. 탐색 높이·범위를 확인하세요.",
        )

    def probe_down_until_torque(
        self,
        task: str,
        anchor: Sequence[float],
        torque_threshold: float,
        max_travel_mm: float,
        baseline_torque: float = 0.0,
        step_mm: float = 0.5,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
    ) -> float:
        """(호환) 노름 기반 — probe_down_until_contact 사용 권장."""
        baseline = [0.0, 0.0, float(baseline_torque), 0.0, 0.0, 0.0]
        contact_z, _ = self.probe_down_until_contact(
            task,
            anchor,
            baseline,
            force_threshold_z=float(torque_threshold),
            max_travel_mm=max_travel_mm,
            step_mm=step_mm,
            vel=vel,
            acc=acc,
        )
        return contact_z

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

    def set_recovery_joint(self, joints: Sequence[float] | None) -> None:
        """실패·중단 시 movej 복귀 조인트 (미설정 시 home_joint)."""
        self._recovery_joint = [float(v) for v in joints] if joints else None

    def movej_joint(
        self,
        joints: Sequence[float],
        label: str,
        task: str,
        vel: float | None = None,
        acc: float | None = None,
    ) -> None:
        self.publish_status(task, label, "running")
        target = self.posj(list(joints))
        v = vel if vel is not None else self._cfg["joint_vel"]
        a = acc if acc is not None else self._cfg["joint_acc"]

        def _move():
            self.movej(target, vel=v, acc=a)

        self._run_with_retry(label, _move)
        self.publish_status(task, label, "done")

    def go_home(self, task: str = "motion") -> None:
        self.movej_joint(self._cfg["home_joint"], "go_home", task)

    def recover_pose(self, task: str = "motion") -> None:
        if self._recovery_joint:
            self.movej_joint(self._recovery_joint, "recover_joint", task)
        else:
            self.go_home(task)

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
        rise_total_mm: float = 0.0,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
    ) -> None:
        """툴 Z축 회전 + 동시 상승으로 그리퍼를 돌리며 들어올림.

        각 스텝을 단일 movel(상대, 툴좌표)로 수행해 회전(rz)과 상승(-Z)이
        동시에 일어나도록 한다 → 자연스러운 개봉 궤적. 나사산 피치에 맞게
        rise_total_mm 를 설정한다.
        """
        if steps <= 0:
            raise MotionError("twist_steps는 1 이상이어야 합니다")
        step_angle = total_deg / steps
        rise_per_step = rise_total_mm / steps
        for index in range(steps):
            self._check_cancel()
            # 회전(툴 Z축 rz)과 상승(툴 -Z)을 한 번의 movel로 동시에 수행
            self.move_relative_tool(
                [0.0, 0.0, -rise_per_step, 0.0, 0.0, step_angle],
                f"{label_prefix}_{index + 1}", task,
                vel=vel, acc=acc,
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
            self.recover_pose(task)
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
