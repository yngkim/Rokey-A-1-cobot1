"""기본 자세에서 TCP Z축 20cm 왕복 동작."""

import rclpy

from cobot1.robot_config import (
    DEFAULT_JOINT_ACC,
    DEFAULT_JOINT_VEL,
    DEFAULT_TASK_ACC,
    DEFAULT_TASK_VEL,
    HOME_JOINT,
)
from cobot1.robot_init import prepare_autonomous_mode, setup

TCP_STROKE_MM = 200.0  # 20cm


def main(args=None):
    setup("move2", args=args)
    prepare_autonomous_mode()

    try:
        from cobot1.motion.dsr_imports import import_dsr_api

        api = import_dsr_api()
        DR_MV_MOD_REL = api["DR_MV_MOD_REL"]
        DR_TOOL = api["DR_TOOL"]
        movej = api["movej"]
        movel = api["movel"]
        posj = api["posj"]
    except ImportError as exc:
        print(f"DSR API import 실패: {exc}")
        return

    home = posj(HOME_JOINT)
    up_delta = [0.0, 0.0, TCP_STROKE_MM, 0.0, 0.0, 0.0]
    down_delta = [0.0, 0.0, -TCP_STROKE_MM, 0.0, 0.0, 0.0]

    print(f"[move2] 기본 자세: {HOME_JOINT}")
    movej(home, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

    while rclpy.ok():
        print(f"[move2] TCP 위로 {TCP_STROKE_MM}mm")
        movel(
            up_delta,
            vel=DEFAULT_TASK_VEL,
            acc=DEFAULT_TASK_ACC,
            ref=DR_TOOL,
            mod=DR_MV_MOD_REL,
        )

        print(f"[move2] TCP 아래로 {TCP_STROKE_MM}mm")
        movel(
            down_delta,
            vel=DEFAULT_TASK_VEL,
            acc=DEFAULT_TASK_ACC,
            ref=DR_TOOL,
            mod=DR_MV_MOD_REL,
        )

    rclpy.shutdown()


if __name__ == "__main__":
    main()
