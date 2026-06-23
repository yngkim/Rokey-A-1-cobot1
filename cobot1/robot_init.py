"""DSR_ROBOT2 초기화 헬퍼."""

import os
import threading
import time

import rclpy
import DR_init

from cobot1.robot_config import ROBOT_ID, ROBOT_MODEL

SERVICE_WAIT_SEC = 30.0

_SPIN_GUARD_INSTALLED = False
_SPIN_LOCK = threading.RLock()


def install_spin_guard() -> None:
    """DSR_ROBOT2 spin_until_future_complete 동시 호출을 직렬화합니다."""
    global _SPIN_GUARD_INSTALLED
    if _SPIN_GUARD_INSTALLED:
        return

    original = rclpy.spin_until_future_complete

    def guarded_spin_until_future_complete(node, future, timeout_sec=None):
        with _SPIN_LOCK:
            if timeout_sec is None:
                return original(node, future)
            return original(node, future, timeout_sec=timeout_sec)

    rclpy.spin_until_future_complete = guarded_spin_until_future_complete
    _SPIN_GUARD_INSTALLED = True


def wait_for_future(
    future,
    timeout_sec: float | None = None,
    poll_interval: float = 0.05,
    node=None,
) -> bool:
    """future 완료 대기. node가 있으면 spin_once로 서비스 응답을 처리합니다."""
    import rclpy

    deadline = None if timeout_sec is None else time.monotonic() + timeout_sec
    while not future.done():
        if deadline is not None and time.monotonic() >= deadline:
            return False
        if node is not None:
            rclpy.spin_once(node, timeout_sec=poll_interval)
        else:
            time.sleep(poll_interval)
    return True


def setup(node_name: str, args=None):
    """ROS2 노드와 DSR API를 초기화합니다.

    DSR_ROBOT2는 import 시점에 DR_init 값을 읽으므로,
    반드시 이 함수 호출 후에 DSR_ROBOT2를 import 하세요.
    """
    install_spin_guard()

    if not rclpy.ok():
        rclpy.init(args=args)

    node = rclpy.create_node(node_name, namespace=ROBOT_ID)
    DR_init.__dsr__id = ROBOT_ID
    DR_init.__dsr__model = ROBOT_MODEL
    DR_init.__dsr__node = node
    return node


def destroy_dsr_node() -> None:
    """DSR 노드를 정리합니다."""
    node = DR_init.__dsr__node
    if node is not None:
        node.destroy_node()
        DR_init.__dsr__node = None


def _wait_for_dsr_services(node, timeout_sec: float = SERVICE_WAIT_SEC) -> None:
    """dsr_controller2 서비스가 준비될 때까지 대기합니다."""
    from dsr_msgs2.srv import SetRobotMode

    client = node.create_client(SetRobotMode, "system/set_robot_mode")
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if client.wait_for_service(timeout_sec=0.5):
            return
        rclpy.spin_once(node, timeout_sec=0.1)

    domain_id = os.environ.get("ROS_DOMAIN_ID", "(미설정)")
    raise RuntimeError(
        f"로봇 제어 서비스를 찾을 수 없습니다 ({timeout_sec:.0f}초 대기).\n"
        f"현재 ROS_DOMAIN_ID={domain_id} (모든 터미널에서 41로 통일 필요)\n"
        "다음을 확인하세요:\n"
        "  1) bringup 터미널과 태스크 터미널의 ROS_DOMAIN_ID가 모두 41인지\n"
        "     (echo $ROS_DOMAIN_ID)\n"
        "  2) bringup을 domain 41로 다시 실행했는지\n"
        "     ros2 launch m0609_rg2_bringup bringup.launch.py mode:=real host:=192.168.1.100\n"
        "  3) 로그에 'Configured and activated dsr_controller2' 가 보이는지\n"
        "  4) 팬던트에서 SERVO ON + 알람 해제 상태인지\n"
        "  5) ros2 service list | grep set_robot_mode 로 서비스 확인"
    )


def prepare_autonomous_mode(timeout_sec: float = SERVICE_WAIT_SEC):
    """자율 모드로 전환 (모션 실행 전 필수)."""
    from cobot1.motion.dsr_imports import import_dsr_api

    node = DR_init.__dsr__node
    if node is None:
        raise RuntimeError("setup()을 먼저 호출하세요.")

    _wait_for_dsr_services(node, timeout_sec)

    api = import_dsr_api()
    result = api["set_robot_mode"](api["ROBOT_MODE_AUTONOMOUS"])
    if result != 0:
        raise RuntimeError(
            "자율 모드 전환 실패. 팬던트에서 SERVO ON 및 외부 제어 모드를 확인하세요."
        )
