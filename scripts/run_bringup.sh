#!/bin/bash
# Doosan M0609 bringup (ROS_DOMAIN_ID=41 고정)
set -euo pipefail

export ROS_DOMAIN_ID=41

source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
exec ros2 launch dsr_bringup2 dsr_bringup2_rviz.launch.py \
  mode:=real host:=192.168.1.100 port:=12345 model:=m0609 "$@"
