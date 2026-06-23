#!/bin/bash
# M0609 + RG2 bringup (m0609_rg2_bringup)
set -eo pipefail

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-41}"

set +u
source /opt/ros/humble/setup.bash
source "${HOME}/ros2_ws/install/setup.bash"
set -u

HOST="${ROBOT_HOST:-192.168.1.100}"
MODE="${ROBOT_MODE:-real}"

echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "bringup: mode=${MODE} host=${HOST}"
echo "  (인자: mode:=real host:=192.168.1.100 — model:= 이 아님 mode:= 입니다)"

exec ros2 launch m0609_rg2_bringup bringup.launch.py \
  "mode:=${MODE}" \
  "host:=${HOST}" \
  "$@"
