"""프론트엔드 연동용 케어 로봇 서버 노드.

ROS2 서비스 (std_srvs/Trigger):
  /dsr01/cobot1/open_bottle
  /dsr01/cobot1/pour_water
  /dsr01/cobot1/pick_place_pill
  /dsr01/cobot1/insert_straw
  /dsr01/cobot1/turn_off_switch
  /dsr01/cobot1/pull_place_tissue
  /dsr01/cobot1/go_home

상태 토픽 (std_msgs/String, JSON):
  /cobot1/status
"""

from __future__ import annotations

import threading

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_srvs.srv import Trigger

from cobot1.robot_config import ROBOT_ID, ROBOT_MODEL
from cobot1.config_loader import load_scenarios
from cobot1.motion.primitives import MotionContext, RobotMotion
from cobot1.robot_init import prepare_autonomous_mode
from cobot1.task_runner import TASK_REGISTRY, _ensure_registry


class CareRobotServer(Node):
    def __init__(self):
        super().__init__("care_robot_server", namespace=ROBOT_ID)
        self.declare_parameter("config_path", "")
        self._lock = threading.Lock()
        self._busy = False

        _ensure_registry()

        config_path = self.get_parameter("config_path").get_parameter_value().string_value
        self._config_path = config_path or None
        self._scenarios = load_scenarios(self._config_path)

        DR_init_node = self
        import DR_init

        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL
        DR_init.__dsr__node = DR_init_node

        prepare_autonomous_mode()
        self._motion = RobotMotion(
            MotionContext(
                node=self,
                motion_cfg=self._scenarios["motion"],
                gripper_cfg=self._scenarios["gripper"],
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
        self.create_service(
            Trigger,
            "cobot1/go_home",
            self._handle_go_home,
            callback_group=group,
        )
        self.get_logger().info("CareRobotServer 준비 완료")

    def _handle_go_home(self, request, response):
        del request
        with self._lock:
            if self._busy:
                response.success = False
                response.message = "다른 작업 실행 중"
                return response
            self._busy = True
        try:
            self._motion.go_home("manual")
            response.success = True
            response.message = "홈 위치 이동 완료"
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        finally:
            self._busy = False
        return response

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
            response.message = result.message
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
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
