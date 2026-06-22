#!/bin/bash
# 침상 케어 로봇 웹 스택 실행 가이드
set -e

echo "=== 1. ROS2 환경 ==="
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo ""
echo "아래를 각각 별도 터미널에서 실행하세요:"
echo ""
echo "# 터미널 1: 로봇 (시뮬 또는 실기)"
echo "ros2 launch dsr_bringup2 dsr_bringup2_rviz.launch.py mode:=real host:=192.168.1.100 model:=m0609"
echo ""
echo "# 터미널 2: 케어 태스크 서버"
echo "ros2 run cobot1 care_server"
echo ""
echo "# 터미널 3: 웹 API 브릿지"
echo "pip install -r ~/ros2_ws/src/cobot1/requirements-web.txt"
echo "ros2 run cobot1 care_web_api"
echo ""
echo "# 터미널 4: React 개발 서버"
echo "cd ~/ros2_ws/src/cobot1/web && npm install && npm run dev"
echo ""
echo "스마트폰/PC 브라우저: http://<PC_IP>:5173"
