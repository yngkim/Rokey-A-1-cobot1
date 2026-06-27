"""프론트엔드 연동용 케어 로봇 서버 (4대 핵심 기능).

ROS2 서비스: /dsr01/cobot1/{task_name}
상태 토픽: /dsr01/cobot1/status, /dsr01/cobot1/safety_alert
"""

from __future__ import annotations

import threading

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_srvs.srv import Trigger

from cobot1.bridge.handoff_gate import ensure_handoff_gate
from cobot1.robot_config import ROBOT_ID
from cobot1.config_loader import load_scenarios
from cobot1.motion.primitives import MotionContext, RobotMotion
from cobot1.robot_init import destroy_dsr_node, prepare_autonomous_mode, setup
from cobot1.task_runner import TASK_REGISTRY, _ensure_registry


class CareRobotServer(Node):
    def __init__(self):
        super().__init__("care_robot_server", namespace=ROBOT_ID)
        self.declare_parameter("config_path", "")
        self._lock = threading.Lock()
        self._busy = False

        _ensure_registry()
        ensure_handoff_gate()

        config_path = self.get_parameter("config_path").get_parameter_value().string_value
        self._config_path = config_path or None
        self._scenarios = load_scenarios(self._config_path)

        from cobot1.robot_init import setup

        self._dsr_node = setup("care_dsr_client")
        prepare_autonomous_mode()
        self._motion = RobotMotion(
            MotionContext(
                node=self._dsr_node,
                motion_cfg=self._scenarios["motion"],
                gripper_cfg=self._scenarios["gripper"],
                safety_cfg=self._scenarios.get("safety", {}),
            )
        )

        group = ReentrantCallbackGroup()
        for task_name in TASK_REGISTRY:
            self.create_service(
                Trigger,
                f"cobot1/{task_name}",
                lambda req, res, name=task_name: self._handle_task(req, res, name),
                callback_group=group,
            )
        self.get_logger().info("CareRobotServer 준비 완료")

    def shutdown(self) -> None:
        if hasattr(self, "_motion"):
            self._motion.shutdown()
        destroy_dsr_node()

    def _handle_task(self, request, response, task_name: str):
        del request
        with self._lock:
            if self._busy:
                response.success = False
                response.message = "다른 작업 실행 중"
                return response
            self._busy = True

        try:
            self._scenarios = load_scenarios(self._config_path)
            task_cls = TASK_REGISTRY[task_name]
            task = task_cls(self._scenarios, self._motion)
            result = task.run()
            response.success = result.success
            response.message = result.user_message or result.message
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        finally:
            self._busy = False
        return response


def main(args=None):
    rclpy.init(args=args)
    node = CareRobotServer()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
