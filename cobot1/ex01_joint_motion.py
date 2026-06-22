"""매뉴얼 2.1.1 posj(), 2.3.1 movej() 예제."""

import rclpy

from cobot1.robot_config import DEFAULT_JOINT_ACC, DEFAULT_JOINT_VEL, HOME_JOINT
from cobot1.robot_init import prepare_autonomous_mode, setup


def main(args=None):
    setup("ex01_joint_motion", args=args)
    prepare_autonomous_mode()

    from cobot1.motion.dsr_imports import import_dsr_api

    api = import_dsr_api()
    movej = api["movej"]
    posj = api["posj"]

    # 매뉴얼 예제
    # q1 = posj()
    # q2 = posj(0, 0, 90, 0, 90, 0)
    # q3 = posj([0, 30, 60, 0, 90, 0])
    home = posj(HOME_JOINT)
    target = posj(0.0, 0.0, 60.0, 0.0, 90.0, 0.0)

    while rclpy.ok():
        print(f"[ex01] movej -> {target}")
        movej(target, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

        print(f"[ex01] movej -> {home}")
        movej(home, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

    rclpy.shutdown()


if __name__ == "__main__":
    main()
