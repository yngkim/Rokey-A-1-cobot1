#!/bin/bash
# 침상 케어 로봇 웹 스택 실행 가이드
set -e

export ROS_DOMAIN_ID=41

echo "=== ROS2 환경 (ROS_DOMAIN_ID=${ROS_DOMAIN_ID}) ==="
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

echo ""
echo "아래를 각각 별도 터미널에서 실행하세요:"
echo ""
echo "# 터미널 1: 로봇 bringup"
echo "export ROS_DOMAIN_ID=41"
echo "ros2 launch m0609_rg2_bringup bringup.launch.py mode:=real host:=192.168.1.100"
echo ""
echo "# 터미널 2: 웹 API (태스크 직접 실행 — care_server 불필요)"
echo "~/ros2_ws/src/cobot1/scripts/run_care_web_api.sh"
echo "  (주의: source는 ~/ros2_ws/install/setup.bash — src/install 아님)"
echo "  → 브라우저: http://<PC_IP>:8080"
echo ""
echo "# (선택) 터미널 3: React 개발 서버 (핫리로드)"
echo "cd ~/ros2_ws/src/cobot1/web && npm install && npm run dev"
echo "  → 브라우저: http://<PC_IP>:5173  (API는 8080으로 프록시)"
echo ""
echo "웹 버튼 = 터미널의 ros2 run cobot1 <태스크명> 과 동일하게 동작합니다."
