"""재시도·안전 복귀·외력 감시·사용자 정지가 포함된 공통 모션 프리미티브."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from rclpy.node import Node
from std_msgs.msg import String

from cobot1.motion.exceptions import (
    CobotError,
    MotionError,
    ObjectMissingError,
    SafetyViolation,
    TaskCancelled,
)
from cobot1.motion.gripper import Gripper
from cobot1.motion.pose_utils import flatten_pose_values
from cobot1.motion.safety import SafetyGuard
from cobot1.motion.safety_decision import (
    prepare_resume_after_external_force,
    wait_for_safety_decision,
)


def _normalize_joint_angle(deg: float) -> float:
    while deg > 180.0:
        deg -= 360.0
    while deg < -180.0:
        deg += 360.0
    return deg


def _j6_delta_deg(current: float, reference: float) -> float:
    return _normalize_joint_angle(current - reference)


def _j6_needs_unwind(
    j6: float,
    ref_j6: float,
    *,
    abs_limit_deg: float,
    delta_limit_deg: float,
) -> bool:
    if abs(j6) > abs_limit_deg:
        return True
    return abs(_j6_delta_deg(j6, ref_j6)) > delta_limit_deg


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
        self._move_stop_client = None
        self._move_stop_request = None
        self._import_motion_api()

    @property
    def gripper(self) -> Gripper:
        return self._gripper

    @property
    def safety(self) -> SafetyGuard:
        return self._safety

    def pause_safety_force_abort(self) -> None:
        """의도적 접촉·파지 구간 — 외력 초과 안전 중단 일시 해제."""
        self._safety.begin_contact_search()

    def resume_safety_force_abort(self) -> None:
        self._safety.end_contact_search()

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
        self._call_move_stop()
        self._safety.request_move_stop()

    def _call_move_stop(self) -> None:
        """메인 DSR 노드에서 move_stop 호출 (블로킹 movel 중단)."""
        from dsr_msgs2.srv import MoveStop

        from cobot1.robot_init import wait_for_future

        if self._move_stop_client is None:
            self._move_stop_client = self._node.create_client(
                MoveStop, "motion/move_stop"
            )
            self._move_stop_request = MoveStop.Request()
        client = self._move_stop_client
        if not client.wait_for_service(timeout_sec=0.5):
            self._node.get_logger().warn("motion/move_stop 서비스 없음 (local)")
            return
        future = client.call_async(self._move_stop_request)
        wait_for_future(future, timeout_sec=2.0, node=self._node)

    def user_stop_recover(
        self,
        task: str,
        *,
        stopped_step: str = "user_stop",
        stopped_message: str = "작업을 중지하고 홈으로 복귀합니다.",
    ) -> None:
        """정지 후 홈 조인트 복귀 (recovery_joint 무시)."""
        self._safety.clear_external_force_violation()
        self.clear_cancel()
        self.publish_status(
            task,
            stopped_step,
            "stopped",
            stopped_message,
            extra={"code": "USER_STOP"},
        )
        try:
            self.gripper.open()
        except Exception as exc:
            self._node.get_logger().warn(f"정지 시 그리퍼 열기 실패: {exc}")
        if self._safety.config.get("enabled", True):
            self._safety.restart_monitor(task)
        self.publish_status(task, "user_stop", "running", "홈 복귀 중")
        try:
            self.go_home(task, label="user_stop_home")
            self.publish_status(task, "user_stop", "recovered", "정지 후 홈 복귀 완료")
        except Exception as exc:
            self._node.get_logger().error(f"정지 후 홈 복귀 실패: {exc}")
            self.publish_status(
                task,
                "user_stop",
                "error",
                f"홈 복귀 실패: {exc}",
                extra={"code": "RECOVERY_FAILED"},
            )

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

    def get_current_tcp_pose(self, *, retries: int = 3) -> list[float]:
        """현재 TCP pose [x,y,z,rx,ry,rz] (DR_BASE, mm/deg)."""
        from cobot1.motion.dsr_imports import import_dsr_api

        api = import_dsr_api()
        last_detail = "unknown"
        for attempt in range(max(1, retries)):
            try:
                pos, _sol = api["get_current_posx"](ref=self.DR_BASE)
            except IndexError as exc:
                last_detail = str(exc)
                time.sleep(0.12)
                continue
            if pos is None or (isinstance(pos, int) and pos in (-1, 0)):
                last_detail = "service returned empty pose"
                time.sleep(0.12)
                continue
            raw = flatten_pose_values(pos)
            if len(raw) < 6:
                last_detail = f"pose length={len(raw)}"
                time.sleep(0.12)
                continue
            return raw[:6]
        raise MotionError(
            f"TCP 위치를 읽을 수 없습니다 ({last_detail}).",
            code="POSE_READ_FAILED",
            user_message="로봇 좌표 조회에 실패했습니다.",
        )

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

    def get_current_joint(self, *, retries: int = 3) -> list[float]:
        """현재 조인트 각도 [j1..j6] (deg)."""
        from cobot1.motion.dsr_imports import import_dsr_api

        api = import_dsr_api()
        last_detail = "unknown"
        for _attempt in range(max(1, retries)):
            pos = api["get_current_posj"]()
            if pos is None or (isinstance(pos, int) and pos in (-1, 0)):
                last_detail = "service returned empty joint"
                time.sleep(0.12)
                continue
            raw = flatten_pose_values(pos, min_length=6)
            if len(raw) < 6:
                last_detail = f"joint length={len(raw)}"
                time.sleep(0.12)
                continue
            return raw[:6]
        raise MotionError(
            f"조인트 위치를 읽을 수 없습니다 ({last_detail}).",
            code="JOINT_READ_FAILED",
            user_message="로봇 조인트 조회에 실패했습니다.",
        )

    def move_base_x_delta(
        self,
        dx_mm: float,
        label: str,
        task: str,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
    ) -> None:
        """베이스 좌표계 X만 이동 (수평, Y·Z·자세 유지)."""
        self.move_relative_base(
            [float(dx_mm), 0.0, 0.0, 0.0, 0.0, 0.0],
            label,
            task,
            vel=vel,
            acc=acc,
        )

    def move_base_z_delta(
        self,
        dz_mm: float,
        label: str,
        task: str,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
    ) -> None:
        """베이스 좌표계 Z만 이동 (수직 하강/상승, 자세 유지)."""
        self.move_relative_base(
            [0.0, 0.0, float(dz_mm), 0.0, 0.0, 0.0],
            label,
            task,
            vel=vel,
            acc=acc,
        )

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
            # 접촉은 스텝 movel 완료 후 판정되므로 move_stop 은 불필요하며,
            # 호출 시 다음 movel 이 즉시 반환만 하고 실제 Z 이동이 안 일어날 수 있다.
            self.mwait(0)
            time.sleep(0.05)
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
                    if self._cancel.is_set():
                        raise TaskCancelled("사용자가 작업을 중단했습니다.")
                    raise MotionError(
                        f"{label}: 모션 완료 확인 실패",
                        code="MOTION_INCOMPLETE",
                        user_message="동작이 완료되지 않았습니다. 로봇 상태를 확인해 주세요.",
                    )
                return
            except (SafetyViolation, TaskCancelled):
                raise
            except Exception as exc:
                if self._cancel.is_set():
                    raise TaskCancelled("사용자가 작업을 중단했습니다.") from exc
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

    def move_joint_via_lift(
        self,
        joints: Sequence[float],
        label: str,
        task: str,
        cfg: dict | None = None,
    ) -> None:
        """목표 조인트로 Z 상승 → XY 이동 → Z 하강 (장애물 회피)."""
        from cobot1.motion.dsr_imports import import_dsr_api

        opts = cfg or {}
        lift_mm = float(
            opts.get("lift_clearance_mm", self._cfg.get("home_lift_clearance_mm", 150.0))
        )
        carry_vel = list(opts.get("carry_vel", self._cfg.get("home_carry_vel", self._cfg["task_vel"])))
        carry_acc = list(opts.get("carry_acc", self._cfg.get("home_carry_acc", self._cfg["task_acc"])))
        descend_vel = list(
            opts.get("descend_vel", self._cfg.get("home_descend_vel", [15, 10]))
        )
        descend_acc = list(
            opts.get("descend_acc", self._cfg.get("home_descend_acc", [30, 20]))
        )

        tcp = flatten_pose_values(import_dsr_api()["fkin"](list(joints)))
        if len(tcp) < 6:
            raise MotionError(
                "목표 조인트의 TCP 변환에 실패했습니다.",
                code="FKIN_FAILED",
                user_message="로봇 좌표 계산에 실패했습니다.",
            )
        cur = self.get_current_tcp_pose()
        travel_z = max(cur[2], tcp[2]) + lift_mm

        self.move_vertical_to_z(
            travel_z, cur, f"{label}_lift", task, vel=carry_vel, acc=carry_acc
        )
        self.move_task_pose(
            [tcp[0], tcp[1], travel_z, tcp[3], tcp[4], tcp[5]],
            f"{label}_travel",
            task,
            vel=carry_vel,
            acc=carry_acc,
        )
        self.move_task_pose(
            tcp, f"{label}_descend", task, vel=descend_vel, acc=descend_acc
        )

    def go_home(
        self,
        task: str = "motion",
        *,
        label: str = "go_home",
        lift_mm: float | None = None,
        joint_vel: float | None = None,
        joint_acc: float | None = None,
        cfg: dict | None = None,
    ) -> None:
        """현재 위치에서 Z 상승 후 홈 조인트로 복귀 (장애물 회피)."""
        home_joint = self._cfg["home_joint"]
        lift_cfg = dict(cfg or {})
        if lift_mm is not None:
            lift_cfg["lift_clearance_mm"] = lift_mm
        self.move_joint_via_lift(home_joint, label, task, lift_cfg)
        v = joint_vel if joint_vel is not None else self._cfg["joint_vel"]
        a = joint_acc if joint_acc is not None else self._cfg["joint_acc"]
        self.movej_joint(home_joint, f"{label}_align", task, vel=v, acc=a)

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

    def move_relative_base(
        self,
        delta: Sequence[float],
        label: str,
        task: str,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
    ) -> None:
        """베이스 좌표계 상대 직선 이동 (손목 자세와 무관하게 베이스 축 이동)."""
        self.publish_status(task, label, "running")
        v = vel or self._cfg["task_vel"]
        a = acc or self._cfg["task_acc"]

        def _move():
            self.movel(
                list(delta),
                vel=v,
                acc=a,
                ref=self.DR_BASE,
                mod=self.DR_MV_MOD_REL,
            )

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

    def rotate_tool_z_steps_guarded(
        self,
        total_deg: float,
        steps: int,
        label_prefix: str,
        task: str,
        pause_sec: float = 0.15,
        rise_total_mm: float = 0.0,
        vel: Sequence[float] | None = None,
        acc: Sequence[float] | None = None,
        *,
        j6_abs_limit_deg: float = 170.0,
        j6_delta_limit_deg: float = 120.0,
        on_j6_unwind: Callable[[], None] | None = None,
    ) -> None:
        """툴 Z 회전을 1스텝씩 수행하며 J6 한계 근접 시 unwind 콜백 호출."""
        if steps <= 0:
            raise MotionError("twist_steps는 1 이상이어야 합니다")
        step_angle = total_deg / steps
        rise_per_step = rise_total_mm / steps
        ref_j6 = self.get_current_joint()[5]
        for index in range(steps):
            self._check_cancel()
            self.move_relative_tool(
                [0.0, 0.0, -rise_per_step, 0.0, 0.0, step_angle],
                f"{label_prefix}_{index + 1}", task,
                vel=vel, acc=acc,
            )
            if pause_sec > 0 and index < steps - 1:
                self.interruptible_sleep(pause_sec)
            j6 = self.get_current_joint()[5]
            if on_j6_unwind is not None and _j6_needs_unwind(
                j6,
                ref_j6,
                abs_limit_deg=j6_abs_limit_deg,
                delta_limit_deg=j6_delta_limit_deg,
            ):
                on_j6_unwind()
                ref_j6 = self.get_current_joint()[5]

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

        self._safety.clear_external_force_violation()
        self.clear_cancel()
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
        safety_cfg = self._safety.config
        steps_list = list(steps)
        try:
            idx = 0
            while idx < len(steps_list):
                step_name, step_action = steps_list[idx]
                while True:
                    try:
                        self._safety.check_or_raise()
                        self._check_cancel()
                        step_action()
                        self._safety.check_or_raise()
                        break
                    except TaskCancelled as exc:
                        self.user_stop_recover(
                            task,
                            stopped_step=step_name,
                            stopped_message=exc.user_message or "작업을 중지했습니다.",
                        )
                        raise
                    except SafetyViolation as exc:
                        if exc.code != "EXTERNAL_FORCE":
                            self.publish_status(
                                task,
                                step_name,
                                "error",
                                exc.user_message,
                                extra={"code": exc.code},
                            )
                            self.safe_abort(task, exc.user_message, exc.code)
                            raise
                        try:
                            decision = wait_for_safety_decision(
                                self,
                                task,
                                step_name,
                                exc,
                                safety_cfg,
                            )
                        except TaskCancelled as cancel_exc:
                            self.user_stop_recover(
                                task,
                                stopped_step=step_name,
                                stopped_message=(
                                    cancel_exc.user_message
                                    or "작업을 중지하고 홈으로 복귀합니다."
                                ),
                            )
                            raise
                        if decision == "resume":
                            prepare_resume_after_external_force(
                                self,
                                task,
                                step_name,
                                safety_cfg,
                            )
                            continue
                        if decision in ("home", "abort"):
                            self.user_stop_recover(
                                task,
                                stopped_step=step_name,
                                stopped_message="외력 감지 — 작업을 중지하고 홈으로 복귀합니다.",
                            )
                            raise TaskCancelled(
                                "외력 감지 후 작업을 중지했습니다.",
                                user_message="외력 감지 — 작업을 중지하고 홈으로 복귀합니다.",
                            ) from exc
                    except CobotError as exc:
                        user_msg = exc.user_message or str(exc)
                        extra: dict[str, Any] = {"code": exc.code}
                        if isinstance(exc, ObjectMissingError):
                            extra["speech_text"] = exc.speech_text
                            extra["object_id"] = exc.object_id
                            extra["object_label"] = exc.object_label
                        self.publish_status(
                            task,
                            step_name,
                            "error",
                            user_msg,
                            extra=extra,
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
                        raise MotionError(
                            str(exc),
                            code="UNKNOWN_ERROR",
                            user_message=user_msg,
                        ) from exc
                idx += 1
        finally:
            self._safety.stop()
