#!/bin/bash
# 웹 API 서버 실행 (환경 자동 설정)
set -eo pipefail

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-41}"

set +u
source /opt/ros/humble/setup.bash
source "${HOME}/ros2_ws/install/setup.bash"
set -u

export PYTHONPATH="${PYTHONPATH:-}:${HOME}/ros2_ws/install/dsr_common2/lib/dsr_common2/imp"

if ! ros2 pkg executables cobot1 2>/dev/null | grep -q care_web_api; then
  echo "care_web_api가 설치되지 않았습니다. 클린 빌드 중..."
  rm -rf "${HOME}/ros2_ws/build/cobot1" "${HOME}/ros2_ws/install/cobot1"
  cd "${HOME}/ros2_ws"
  colcon build --packages-select cobot1
  source "${HOME}/ros2_ws/install/setup.bash"
fi

if ! python3 -c "from importlib.metadata import distribution; distribution('cobot1')" 2>/dev/null; then
  echo "cobot1 패키지 메타데이터가 없습니다. 재빌드 중..."
  cd "${HOME}/ros2_ws"
  colcon build --packages-select cobot1
  source "${HOME}/ros2_ws/install/setup.bash"
fi

REQ="${HOME}/ros2_ws/src/cobot1/requirements-web.txt"
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "FastAPI 설치 중..."
  pip3 install --user -r "${REQ}"
fi

if ! python3 -c "import edge_tts" 2>/dev/null; then
  echo "edge-tts 설치 중 (미디어 TTS)..."
  pip3 install --user edge-tts
fi

echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "웹 UI: http://$(hostname -I | awk '{print $1}'):8080"
exec ros2 run cobot1 care_web_api "$@"
