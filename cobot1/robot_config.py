"""M0609 시뮬레이터 공통 설정 (Programming Manual V3.4.0 기준)."""

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"

# 조인트 모션 기본값 [deg/s, deg/s^2]
DEFAULT_JOINT_VEL = 30
DEFAULT_JOINT_ACC = 30

# 태스크 모션 기본값 [mm/s, deg/s], [mm/s^2, deg/s^2]
DEFAULT_TASK_VEL = [100, 50]
DEFAULT_TASK_ACC = [200, 100]

# 매뉴얼 예제에서 자주 쓰는 홈 자세: posj(0, 0, 90, 0, 90, 0)
HOME_JOINT = [0.0, 0.0, 90.0, 0.0, 90.0, 0.0]

# M0609 작업 공간 예제 좌표 (매뉴얼 2.1.2, 2.3.2 예제 변형)
TASK_POSE_1 = [400.0, 300.0, 500.0, 0.0, 180.0, 0.0]
TASK_POSE_2 = [400.0, 300.0, 350.0, 0.0, 180.0, 0.0]
TASK_POSE_START = [564.0, 34.5, 690.0, 0.0, 180.0, 0.0]
