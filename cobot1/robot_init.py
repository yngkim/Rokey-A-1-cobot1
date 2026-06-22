"""DSR_ROBOT2 초기화 헬퍼."""

import rclpy
import DR_init

from cobot1.robot_config import ROBOT_ID, ROBOT_MODEL


def setup(node_name: str, args=None):
    """ROS2 노드와 DSR API를 초기화합니다.

    DSR_ROBOT2는 import 시점에 DR_init 값을 읽으므로,
    반드시 이 함수 호출 후에 DSR_ROBOT2를 import 하세요.
    """
    if not rclpy.ok():
        rclpy.init(args=args)

    node = rclpy.create_node(node_name, namespace=ROBOT_ID)
    DR_init.__dsr__id = ROBOT_ID
    DR_init.__dsr__model = ROBOT_MODEL
    DR_init.__dsr__node = node
    return node


def prepare_autonomous_mode():
    """자율 모드로 전환 (모션 실행 전 필수)."""
    from cobot1.motion.dsr_imports import import_dsr_api

    api = import_dsr_api()
    api["set_robot_mode"](api["ROBOT_MODE_AUTONOMOUS"])
