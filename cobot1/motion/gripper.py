"""그리퍼 추상화 — 시뮬레이터/실기 동일 인터페이스."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rclpy.node import Node


class Gripper:
    def __init__(self, node: Node | None, cfg: dict):
        self._node = node
        self._simulated = bool(cfg.get("simulated", True))
        self._settle = float(cfg.get("settle_time_sec", 0.5))
        self._closed = False

    @property
    def is_simulated(self) -> bool:
        return self._simulated

    @property
    def is_closed(self) -> bool:
        return self._closed

    def _log(self, message: str) -> None:
        if self._node is not None:
            self._node.get_logger().info(message)
        else:
            print(message)

    def open(self) -> None:
        if self._simulated:
            self._log("[gripper:sim] 열기")
        else:
            from cobot1.motion.dsr_imports import import_dsr_api

            api = import_dsr_api()
            api["set_tool_digital_output"](1, False)
            self._log("[gripper:real] 열기")
        self._closed = False
        time.sleep(self._settle)

    def close(self) -> None:
        if self._simulated:
            self._log("[gripper:sim] 닫기")
        else:
            from cobot1.motion.dsr_imports import import_dsr_api

            api = import_dsr_api()
            api["set_tool_digital_output"](1, True)
            self._log("[gripper:real] 닫기")
        self._closed = True
        time.sleep(self._settle)
