#!/bin/bash
# (선택) 별도 그리퍼 드라이버 — m0609_rg2_bringup 실기 모드에서는 불필요
# bringup이 OnRobotRGControllerServer를 이미 실행합니다.
set -eo pipefail

export ROS_DOMAIN_ID=41

# set -u 와 ROS setup.bash 충돌 방지 (AMENT_TRACE_SETUP_FILES)
set +u
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
set -u

GRIPPER_IP="${GRIPPER_IP:-192.168.1.1}"
GRIPPER_PORT="${GRIPPER_PORT:-502}"

if ! python3 -c "from pymodbus.client import ModbusTcpClient" 2>/dev/null; then
  echo "pymodbus 설치 중..."
  pip3 install --user pymodbus
fi

echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "OnRobot RG2 driver → ${GRIPPER_IP}:${GRIPPER_PORT}"

exec ros2 run onrobot_rg_control OnRobotRGControllerServer --ros-args \
  -p /onrobot/control:=modbus \
  -p /onrobot/ip:="${GRIPPER_IP}" \
  -p /onrobot/port:="${GRIPPER_PORT}" \
  -p /onrobot/changer_addr:=65 \
  -p /onrobot/gripper:=rg2 \
  -p /onrobot/offset:=5 \
  --remap /joint_states:=/onrobot_joint_states
