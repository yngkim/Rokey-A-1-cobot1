"""OnRobot RG2 Modbus/TCP 직접 제어 (별도 ROS 드라이버 노드 불필요)."""

from __future__ import annotations

import math
import threading
from typing import Any

from cobot1.motion.exceptions import MotionError

# RG2 기하 (onrobot_rg_control OnRobotRGNode 와 동일)
_L1 = 0.108505
_L3 = 0.055
_THETA1 = 1.41371
_THETA3 = 0.76794
_DY = -0.0144
_DEFAULT_MAX_FORCE = 400
_DEFAULT_MAX_WIDTH = 1100
_RCTR_MOVE = 16


def _width_to_joint(width_m: float) -> float:
    return math.acos(((width_m / 2) - _DY - _L1 * math.cos(_THETA1)) / _L3) - _THETA3


def _joint_to_width(joint_angle: float) -> float:
    return (math.cos(joint_angle + _THETA3) * _L3 + _DY + _L1 * math.cos(_THETA1)) * 2


class Rg2ModbusClient:
    """RG2 그리퍼 Modbus/TCP 클라이언트."""

    def __init__(self, cfg: dict):
        self._ip = str(cfg.get("modbus_ip", "192.168.1.1"))
        self._port = int(cfg.get("modbus_port", 502))
        self._changer_addr = int(cfg.get("changer_addr", 65))
        self._max_force = int(cfg.get("force", _DEFAULT_MAX_FORCE))
        self._max_width = int(cfg.get("max_width", _DEFAULT_MAX_WIDTH))
        self._timeout = float(cfg.get("modbus_timeout_sec", 2.0))
        self._client: Any = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        if self._client is not None and self._client.connected:
            return

        try:
            from pymodbus.client import ModbusTcpClient
        except ImportError as exc:
            raise MotionError(
                "pymodbus 패키지가 없습니다.",
                code="GRIPPER_DEPENDENCY_MISSING",
                user_message="pip3 install --user pymodbus 를 실행하세요.",
            ) from exc

        self._client = ModbusTcpClient(
            host=self._ip,
            port=self._port,
            timeout=self._timeout,
        )
        if not self._client.connect():
            raise MotionError(
                f"RG2 Modbus 연결 실패: {self._ip}:{self._port}",
                code="GRIPPER_CONNECT_FAILED",
                user_message="그리퍼 전원·케이블·IP(기본 192.168.1.1)를 확인하세요.",
            )

    def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _write_command(self, force: int, width_units: int, command_type: int) -> None:
        self.connect()
        joint_angle = _width_to_joint(width_units / 10000.0)
        width_register = int(_joint_to_width(joint_angle) * 10000)
        values = [int(force), width_register, int(command_type)]

        with self._lock:
            assert self._client is not None
            result = self._client.write_registers(
                address=0,
                values=values,
                device_id=self._changer_addr,
            )

        if result.isError():
            raise MotionError(
                f"RG2 Modbus 명령 실패: {result}",
                code="GRIPPER_COMMAND_FAILED",
                user_message="그리퍼가 명령을 받지 못했습니다.",
            )

    def open(self) -> None:
        self._write_command(self._max_force, self._max_width, _RCTR_MOVE)

    def close(self) -> None:
        self._write_command(self._max_force, 0, _RCTR_MOVE)
