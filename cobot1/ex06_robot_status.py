"""매뉴얼 3장 상태 조회 (get_current_posj/posx, check_motion) 예제."""

import rclpy

from cobot1.robot_config import DEFAULT_JOINT_ACC, DEFAULT_JOINT_VEL, HOME_JOINT
from cobot1.robot_init import prepare_autonomous_mode, setup


def print_status(api):
    current_joint = api["get_current_posj"]()
    current_task = api["get_current_posx"]()
    motion_done = api["check_motion"]()

    print(f"  현재 관절각: {current_joint}")
    print(f"  현재 TCP 좌표: {current_task}")
    print(f"  모션 완료 여부: {motion_done}")


def main(args=None):
    setup("ex06_robot_status", args=args)
    prepare_autonomous_mode()

    from cobot1.motion.dsr_imports import import_dsr_api

    api = import_dsr_api()
    status_api = {
        "get_current_posj": api["get_current_posj"],
        "get_current_posx": api["get_current_posx"],
        "check_motion": api["check_motion"],
    }

    home = api["posj"](HOME_JOINT)
    target = api["posj"](0.0, 30.0, 75.0, 0.0, 90.0, 0.0)

    print("[ex06] 초기 상태")
    print_status(status_api)

    while rclpy.ok():
        print("[ex06] 목표 관절로 이동 중...")
        api["movej"](target, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

        print("[ex06] 이동 중 상태")
        print_status(status_api)

        api["mwait"](0)
        print("[ex06] 모션 완료 후 상태")
        print_status(status_api)

        api["movej"](home, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)
        api["mwait"](0)

    rclpy.shutdown()


if __name__ == "__main__":
    main()
