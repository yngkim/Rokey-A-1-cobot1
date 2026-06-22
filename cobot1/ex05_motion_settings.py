"""매뉴얼 2.2 모션 설정 (set_velj/accj/velx/accx) 예제."""

import rclpy

from cobot1.robot_config import HOME_JOINT
from cobot1.robot_init import prepare_autonomous_mode, setup


def main(args=None):
    setup("ex05_motion_settings", args=args)
    prepare_autonomous_mode()

    from cobot1.motion.dsr_imports import import_dsr_api

    api = import_dsr_api()
    movej = api["movej"]
    movel = api["movel"]
    set_accj = api["set_accj"]
    set_accx = api["set_accx"]
    set_velj = api["set_velj"]
    set_velx = api["set_velx"]
    posj = api["posj"]
    posx = api["posx"]

    q_home = posj(HOME_JOINT)
    q_target = posj(0.0, 0.0, 60.0, 0.0, 90.0, 0.0)
    p_high = posx(400.0, 500.0, 600.0, 0.0, 180.0, 0.0)
    p_low = posx(400.0, 500.0, 400.0, 0.0, 180.0, 0.0)

    # 매뉴얼 2.2.1, 2.2.2 조인트 전역 속도/가속도
    set_velj(30)
    set_accj(60)

    # 매뉴얼 2.2.3, 2.2.4 태스크 전역 속도/가속도
    set_velx(30, 20)
    set_accx(60, 40)

    while rclpy.ok():
        print("[ex05] 전역 속도로 movej (vel/acc 미지정)")
        movej(q_target)

        print("[ex05] 지정 속도로 movej")
        movej(q_home, vel=20, acc=40)

        movej(q_home, vel=30, acc=30)
        movel(p_high, vel=10, acc=20)

        print("[ex05] 전역 속도로 movel")
        movel(p_low)

        print("[ex05] 지정 속도로 movel")
        movel(p_high, vel=20, acc=40)

    rclpy.shutdown()


if __name__ == "__main__":
    main()
