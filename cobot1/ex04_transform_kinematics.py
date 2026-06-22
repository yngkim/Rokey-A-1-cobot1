"""매뉴얼 2.1.3 trans(), 2.1.5 fkin(), 2.1.6 ikin() 예제."""

import rclpy

from cobot1.robot_config import (
    DEFAULT_JOINT_ACC,
    DEFAULT_JOINT_VEL,
    DEFAULT_TASK_ACC,
    DEFAULT_TASK_VEL,
    HOME_JOINT,
)
from cobot1.robot_init import prepare_autonomous_mode, setup


def main(args=None):
    setup("ex04_transform_kinematics", args=args)
    prepare_autonomous_mode()

    from cobot1.motion.dsr_imports import import_dsr_api

    api = import_dsr_api()
    DR_BASE = api["DR_BASE"]
    fkin = api["fkin"]
    ikin = api["ikin"]
    movej = api["movej"]
    movel = api["movel"]
    trans = api["trans"]
    posj = api["posj"]
    posx = api["posx"]

    home = posj(HOME_JOINT)
    movej(home, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

    # 2.1.3 trans() - base 좌표계에서 delta만큼 이동
    x1 = posx(200.0, 200.0, 400.0, 0.0, 180.0, 0.0)
    delta = [100.0, 100.0, 0.0, 0.0, 0.0, 0.0]
    x2 = trans(x1, delta, DR_BASE, DR_BASE)
    print(f"[ex04] trans 결과: {x2}")

    # 2.1.5 fkin() - 관절각 -> TCP 좌표
    q_sample = posj(30.0, 0.0, 90.0, 0.0, 90.0, 0.0)
    x_from_joint = fkin(q_sample, DR_BASE)
    print(f"[ex04] fkin 결과: {x_from_joint}")

    # 2.1.6 ikin() - TCP 좌표 -> 관절각 (solution space 2)
    target = posx(400.0, 300.0, 500.0, 0.0, 180.0, 0.0)
    joint_target = ikin(target, 2, DR_BASE)
    print(f"[ex04] ikin 결과: {joint_target}")

    while rclpy.ok():
        print("[ex04] trans 좌표로 직선 이동")
        movel(x2, vel=DEFAULT_TASK_VEL, acc=DEFAULT_TASK_ACC)

        print("[ex04] ikin으로 계산한 관절로 이동")
        movej(joint_target, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

        print("[ex04] fkin 좌표로 직선 이동")
        movel(x_from_joint, vel=DEFAULT_TASK_VEL, acc=DEFAULT_TASK_ACC)

        movej(home, vel=DEFAULT_JOINT_VEL, acc=DEFAULT_JOINT_ACC)

    rclpy.shutdown()


if __name__ == "__main__":
    main()
