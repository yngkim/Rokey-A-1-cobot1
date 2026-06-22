"""매뉴얼 2.1.2 posx(), 2.3.2 movel() 예제."""

import rclpy

from cobot1.robot_config import (
    DEFAULT_JOINT_ACC,
    DEFAULT_JOINT_VEL,
    DEFAULT_TASK_ACC,
    DEFAULT_TASK_VEL,
    HOME_JOINT,
    TASK_POSE_1,
    TASK_POSE_2,
)
from cobot1.robot_init import prepare_autonomous_mode, setup


def main(args=None):
    setup("ex02_linear_motion", args=args)
    prepare_autonomous_mode()

    from cobot1.motion.dsr_imports import import_dsr_api

    api = import_dsr_api()
    movej = api["movej"]
    movel = api["movel"]
    set_accx = api["set_accx"]
    set_velx = api["set_velx"]
    posj = api["posj"]
    posx = api["posx"]

    # 매뉴얼 2.2.3, 2.2.4 전역 태스크 속도/가속도 설정
    set_velx(DEFAULT_TASK_VEL[0], DEFAULT_TASK_VEL[1])
    set_accx(DEFAULT_TASK_ACC[0], DEFAULT_TASK_ACC[1])

    home = posj(HOME_JOINT)
    # x2 = posx(400, 300, 500, 0, 180, 0)
    # x3 = posx([350, 350, 450, 0, 180, 0])
    pose_high = posx(TASK_POSE_1)
    pose_low = posx(TASK_POSE_2)

    while rclpy.ok():
        print("[ex02] 홈 자세로 이동")
        movej(home, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

        print(f"[ex02] movel -> {pose_high}")
        movel(pose_high, vel=DEFAULT_TASK_VEL, acc=DEFAULT_TASK_ACC)

        print(f"[ex02] movel -> {pose_low} (전역 속도 사용)")
        movel(pose_low)

        print("[ex02] 홈 자세로 복귀")
        movej(home, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

    rclpy.shutdown()


if __name__ == "__main__":
    main()
