"""매뉴얼 2.3.4 movec() 예제."""

import rclpy

from cobot1.robot_config import (
    DEFAULT_JOINT_ACC,
    DEFAULT_JOINT_VEL,
    DEFAULT_TASK_ACC,
    DEFAULT_TASK_VEL,
    HOME_JOINT,
    TASK_POSE_START,
)
from cobot1.robot_init import prepare_autonomous_mode, setup


def main(args=None):
    setup("ex03_circle_motion", args=args)
    prepare_autonomous_mode()

    from cobot1.motion.dsr_imports import import_dsr_api

    api = import_dsr_api()
    DR_BASE = api["DR_BASE"]
    movec = api["movec"]
    movej = api["movej"]
    movel = api["movel"]
    posj = api["posj"]
    posx = api["posx"]

    home = posj(HOME_JOINT)
    start = posx(TASK_POSE_START)

    # 매뉴얼 posb/moveb 예제 경로를 단순 원호로 변형
    via = posx(564.0, 200.0, 490.0, 0.0, 180.0, 0.0)
    end = posx(564.0, 300.0, 690.0, 0.0, 180.0, 0.0)

    while rclpy.ok():
        movej(home, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)
        movel(start, vel=DEFAULT_TASK_VEL, acc=DEFAULT_TASK_ACC)

        print("[ex03] movec 원호 이동")
        movec(
            via,
            end,
            vel=DEFAULT_TASK_VEL,
            acc=DEFAULT_TASK_ACC,
            ref=DR_BASE,
        )

        movej(home, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

    rclpy.shutdown()


if __name__ == "__main__":
    main()
