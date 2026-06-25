"""그리퍼 추상화 — 시뮬 / DSR tool IO / OnRobot RG2(Modbus 직접)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from cobot1.motion.exceptions import MotionError

if TYPE_CHECKING:
    from rclpy.node import Node

    from cobot1.motion.rg2_modbus import Rg2ModbusClient

DRIVER_SIMULATED = "simulated"
DRIVER_DSR_DIGITAL = "dsr_digital"
DRIVER_ONROBOT_RG2 = "onrobot_rg2"
DRIVER_ONROBOT_ROS = "onrobot_ros"  # m0609_rg2_bringup /onrobot/sendCommand

# RG2 URDF rg2_finger_joint limits (rad)
DEFAULT_OPEN_POSITION = -0.558505
DEFAULT_CLOSED_POSITION = 0.785398


def resolve_gripper_driver(cfg: dict) -> str:
    if "driver" in cfg:
        return str(cfg["driver"])
    if bool(cfg.get("simulated", True)):
        return DRIVER_SIMULATED
    return DRIVER_ONROBOT_RG2


class Gripper:
    def __init__(self, node: Node | None, cfg: dict):
        self._node = node
        self._cfg = cfg
        self._driver = resolve_gripper_driver(cfg)
        self._settle = float(cfg.get("settle_time_sec", 0.5))
        self._closed = False
        self._rg2: Rg2ModbusClient | None = None
        self._onrobot_client = None
        self._joint_sub = None
        self._joint_positions: dict[str, float] = {}

    @property
    def driver(self) -> str:
        return self._driver

    @property
    def is_simulated(self) -> bool:
        return self._driver == DRIVER_SIMULATED

    @property
    def is_closed(self) -> bool:
        return self._closed

    def _log(self, message: str) -> None:
        if self._node is not None:
            self._node.get_logger().info(message)
        else:
            print(message)

    def _rg2_client(self) -> Rg2ModbusClient:
        if self._rg2 is None:
            from cobot1.motion.rg2_modbus import Rg2ModbusClient

            self._rg2 = Rg2ModbusClient(self._cfg)
        return self._rg2

    def shutdown(self) -> None:
        if self._joint_sub is not None and self._node is not None:
            self._node.destroy_subscription(self._joint_sub)
            self._joint_sub = None
        if self._rg2 is not None:
            self._rg2.disconnect()
            self._rg2 = None

    def _ensure_joint_subscription(self) -> None:
        if self._joint_sub is not None or self._node is None:
            return
        from sensor_msgs.msg import JointState

        topic = str(self._cfg.get("joint_states_topic", "/gripper_joint_states"))
        self._joint_sub = self._node.create_subscription(
            JointState,
            topic,
            self._on_joint_state,
            10,
        )

    def _on_joint_state(self, msg) -> None:
        for name, pos in zip(msg.name, msg.position):
            self._joint_positions[str(name)] = float(pos)

    def _finger_joint_name(self) -> str:
        return str(self._cfg.get("finger_joint_name", "rg2_finger_joint"))

    def _target_position(self, closed: bool) -> float:
        if closed:
            return float(self._cfg.get("closed_joint_position", DEFAULT_CLOSED_POSITION))
        return float(self._cfg.get("open_joint_position", DEFAULT_OPEN_POSITION))

    def _wait_for_joint_motion(
        self, closed: bool, wait_sec: float | None = None,
    ) -> None:
        """sendCommand는 즉시 반환하므로 조인트 피드백까지 대기."""
        settle = float(wait_sec) if wait_sec is not None else self._settle
        if self._driver == DRIVER_ONROBOT_RG2:
            timeout = float(self._cfg.get("motion_timeout_sec", 6.0))
            self._rg2_client().wait_until_idle(
                timeout_sec=timeout,
                min_wait_sec=settle,
            )
            return
        if self._driver not in (DRIVER_ONROBOT_ROS,):
            time.sleep(settle)
            return

        if self._node is None:
            time.sleep(self._settle)
            return

        import rclpy

        self._ensure_joint_subscription()
        target = self._target_position(closed)
        tol = float(self._cfg.get("joint_position_tolerance", 0.03))
        timeout = float(self._cfg.get("motion_timeout_sec", 6.0))
        joint_name = self._finger_joint_name()
        deadline = time.monotonic() + timeout
        last_pos: float | None = None

        while time.monotonic() < deadline:
            rclpy.spin_once(self._node, timeout_sec=0.05)
            pos = self._joint_positions.get(joint_name)
            if pos is not None:
                last_pos = pos
                if abs(pos - target) <= tol:
                    self._log(
                        f"[gripper] 조인트 도달 {joint_name}={pos:.3f} "
                        f"(목표={target:.3f})"
                    )
                    time.sleep(self._settle)
                    return
            time.sleep(0.02)

        if last_pos is None:
            self._log(
                f"[gripper] 조인트 피드백 없음 ({joint_name}) — "
                f"settle {self._settle}s 대기"
            )
            time.sleep(self._settle)
            return

        raise MotionError(
            f"그리퍼 조인트 미도달: {joint_name}={last_pos:.3f}, 목표={target:.3f}",
            code="GRIPPER_MOTION_TIMEOUT",
            user_message="그리퍼가 열리거나 닫히지 않았습니다. 끼임·연결 상태를 확인하세요.",
        )

    def _set_dsr_tool_output(self, closed: bool) -> None:
        from cobot1.motion.dsr_imports import import_dsr_api

        api = import_dsr_api()
        pin = int(self._cfg.get("dsr_tool_pin", 1))
        api["set_tool_digital_output"](pin, closed)

    def _onrobot_ros_command(self, command: str) -> None:
        """m0609_rg2_bringup OnRobotRGControllerServer (/onrobot/sendCommand)."""
        from onrobot_rg_msgs.srv import SetCommand

        from cobot1.robot_init import wait_for_future

        if self._node is None:
            raise MotionError(
                "onrobot_ros 그리퍼는 ROS 노드가 필요합니다.",
                code="GRIPPER_CONFIG_ERROR",
            )

        if self._onrobot_client is None:
            self._onrobot_client = self._node.create_client(
                SetCommand, "/onrobot/sendCommand"
            )

        if not self._onrobot_client.wait_for_service(timeout_sec=5.0):
            raise MotionError(
                "그리퍼 서비스가 없습니다. m0609_rg2_bringup을 먼저 실행하세요.",
                code="GRIPPER_SERVICE_UNAVAILABLE",
                user_message=(
                    "그리퍼 서비스에 연결되지 않았습니다. "
                    "bringup이 실행 중인지 확인해 주세요."
                ),
            )

        req = SetCommand.Request()
        req.command = command
        future = self._onrobot_client.call_async(req)
        if not wait_for_future(future, timeout_sec=30.0, node=self._node):
            raise MotionError(
                "그리퍼 명령 시간 초과",
                code="GRIPPER_TIMEOUT",
                user_message="그리퍼 응답이 없습니다.",
            )
        result = future.result()
        if result is None or not result.success:
            msg = "" if result is None else result.message
            raise MotionError(
                f"그리퍼 명령 실패: {msg}",
                code="GRIPPER_COMMAND_FAILED",
                user_message="그리퍼 동작에 실패했습니다.",
            )

    def open(self) -> None:
        if self._driver == DRIVER_SIMULATED:
            self._log("[gripper:sim] 열기")
        elif self._driver == DRIVER_DSR_DIGITAL:
            self._set_dsr_tool_output(False)
            self._log("[gripper:dsr] 열기")
        elif self._driver == DRIVER_ONROBOT_ROS:
            self._onrobot_ros_command("o")
            self._log("[gripper:onrobot_ros] 열기 명령 전송")
            self._wait_for_joint_motion(closed=False)
        elif self._driver == DRIVER_ONROBOT_RG2:
            self._rg2_client().open()
            self._log("[gripper:rg2] 열기 (modbus)")
            self._wait_for_joint_motion(closed=False)
        else:
            raise MotionError(
                f"알 수 없는 gripper.driver: {self._driver}",
                code="GRIPPER_CONFIG_ERROR",
            )

        self._closed = False

    def close(self) -> None:
        if self._driver == DRIVER_SIMULATED:
            self._log("[gripper:sim] 닫기")
        elif self._driver == DRIVER_DSR_DIGITAL:
            self._set_dsr_tool_output(True)
            self._log("[gripper:dsr] 닫기")
        elif self._driver == DRIVER_ONROBOT_ROS:
            self._onrobot_ros_command("c")
            self._log("[gripper:onrobot_ros] 닫기 명령 전송")
            self._wait_for_joint_motion(closed=True)
        elif self._driver == DRIVER_ONROBOT_RG2:
            self._rg2_client().close()
            self._log("[gripper:rg2] 닫기 (modbus)")
            self._wait_for_joint_motion(closed=True)
        else:
            raise MotionError(
                f"알 수 없는 gripper.driver: {self._driver}",
                code="GRIPPER_CONFIG_ERROR",
            )

        self._closed = True

    def grip(
        self,
        force: float | None = None,
        width_units: int = 0,
        wait_sec: float | None = None,
    ) -> None:
        """지정 힘/너비로 약하게 파지 (뚜껑 변형 방지 등).

        onrobot_rg2(Modbus) 외 드라이버는 일반 close() 로 대체한다.
        wait_sec: Modbus 등 피드백 없는 드라이버의 닫힘 대기 시간(초).
        """
        if self._driver == DRIVER_ONROBOT_RG2:
            self._rg2_client().grip(force, width_units)
            self._log(
                f"[gripper:rg2] 약파지 (force={force}, width_units={width_units}, "
                f"wait={wait_sec if wait_sec is not None else self._settle}s)"
            )
            self._wait_for_joint_motion(closed=True, wait_sec=wait_sec)
            self._closed = True
            return
        self.close()
