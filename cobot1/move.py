"""기본 조인트/직선 모션 예제 (posj + movej + movel)."""

import rclpy

from cobot1.robot_config import DEFAULT_JOINT_ACC, DEFAULT_JOINT_VEL, HOME_JOINT
from cobot1.robot_init import prepare_autonomous_mode, setup


def main(args=None):
    setup("rokey_move", args=args)
    prepare_autonomous_mode()

    try:
        from cobot1.motion.dsr_imports import import_dsr_api

        api = import_dsr_api()
        movej = api["movej"]
        movel = api["movel"]
        posj = api["posj"]
        posx = api["posx"]
    except ImportError as exc:
        print(f"DSR API import 실패: {exc}")
        return

    home = posj(HOME_JOINT)
    task_pose = posx([350.0, 34.5, 300.0, 45.0, 180.0, 45.0])

    while rclpy.ok():
        print(f"조인트 이동: {home}")
        movej(home, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

        print(f"직선 이동: {task_pose}")
        movel(task_pose, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

    rclpy.shutdown()


if __name__ == "__main__":
    main()
