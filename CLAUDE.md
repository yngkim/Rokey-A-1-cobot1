# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 환경 요구 사항

- OS: Ubuntu 22.04, ROS 2 Humble
- 로봇: Doosan M0609 + OnRobot RG2 그리퍼
- Python 3.10+, Node.js 16+ (웹 UI 빌드)
- `ROS_DOMAIN_ID=41` — 모든 터미널에서 반드시 동일해야 함

## 빌드 및 실행

```bash
# 빌드
cd ~/ros2_ws
source /opt/ros/humble/setup.bash
export PYTHONPATH=$PYTHONPATH:~/ros2_ws/install/dsr_common2/lib/dsr_common2/imp
colcon build --symlink-install
source install/setup.bash

# 클린 빌드 (cobot1만)
rm -rf build/cobot1 install/cobot1
colcon build --packages-select cobot1
source install/setup.bash

# 웹 UI 빌드 (변경 시)
cd ~/ros2_ws/src/cobot1/web && npm install && npm run build
```

## 실행 순서

```bash
# 터미널 1: 로봇 bringup (mode:=real — model:=real 아님)
export ROS_DOMAIN_ID=41
source ~/ros2_ws/install/setup.bash
ros2 launch m0609_rg2_bringup bringup.launch.py mode:=real host:=192.168.1.100

# 터미널 2: 웹 API + UI (http://<PC_IP>:8080)
~/ros2_ws/src/cobot1/scripts/run_care_web_api.sh

# 태스크 단독 실행
ros2 run cobot1 open_bottle   # 또는 pour_water, pick_place_pill, place_on_charger, pick_from_charger, go_home
```

## 아키텍처

### 실행 경로: 두 가지 모드

**웹 API 모드** (주 사용 경로):
```
브라우저 → FastAPI (port 8080) → RosBridge 노드
  → WebTaskSession (DSR 세션 유지)
    → TASK_REGISTRY[task_id] → BaseTask._execute()
      → RobotMotion (모션 프리미티브)
        → DSR Python API (movej/movel)
```
- `WebTaskSession`이 DSR 노드를 한 번만 생성하고 태스크 간 재사용 — 두 번째 태스크가 안 될 경우 이 세션 유지 로직을 확인
- WebSocket(`/ws`)으로 `cobot1/status`, `cobot1/safety_alert` 토픽을 실시간 브라우저에 전달

**ROS2 서비스 모드** (선택):
```
ros2 service call → CareRobotServer (std_srvs/Trigger)
  → TASK_REGISTRY[task_name] → BaseTask._execute()
```

**태스크 직접 실행** (`ros2 run cobot1 <task>`):
```
task_runner.run_task() → DSR 노드 생성 → 실행 → 노드 소멸
```

### 핵심 레이어

| 레이어 | 위치 | 역할 |
|--------|------|------|
| **Tasks** | `cobot1/tasks/` | `BaseTask` 상속, `_execute()` 구현, `scenarios.yaml` 읽어 pose 사용 |
| **Motion** | `cobot1/motion/primitives.py` | `RobotMotion`: movej/movel 래핑, 재시도, 취소, 상태 발행 |
| **Safety** | `cobot1/motion/safety.py` | `SafetyGuard`: 별도 노드에서 `msg/tool_force` 구독, 외력 초과 시 abort |
| **Gripper** | `cobot1/motion/gripper.py` | OnRobot RG2 제어 (`/onrobot/sendCommand` 서비스) |
| **Bridge** | `cobot1/bridge/` | FastAPI + WebSocket, `WebTaskSession` |
| **Config** | `config/scenarios.yaml` | 모든 pose(mm/deg), 속도, 안전 한계. `COBOT1_CONFIG` 환경변수로 경로 오버라이드 가능 |

### 태스크 추가 방법

1. `cobot1/tasks/` 에 새 파일 생성, `BaseTask` 상속, `name = "my_task"` 설정, `_execute()` 구현
2. `task_runner.py`의 `_ensure_registry()` 에 import + `register_task()` 추가
3. `setup.py`의 `console_scripts` 에 진입점 추가
4. `config/scenarios.yaml` 에 `my_task:` 섹션 추가 (pose, 파라미터)
5. `bridge/api_server.py`의 `TASK_CATALOG` 에 UI 메타데이터 추가

### 안전 시스템 핵심

- `SafetyGuard`는 `RobotMotion` 내에서 생성, `run_sequence()` 호출 시 자동 시작/종료
- 외력 감시는 **별도 스레드의 별도 ROS 노드**(`cobot1_safety_monitor`)가 `dsr01/msg/tool_force` 토픽을 구독 — DSR API의 동일 노드 중복 spin 제한 때문
- 접촉 탐색 중(`probe_down_until_contact`)에는 `begin_contact_search()` / `end_contact_search()`로 외력 abort를 일시 해제
- 위반 감지 시 흐름: `SafetyViolation` 예외 → `BaseTask.run()`이 catch → `TaskResult(success=False)` 반환 → 웹 alert 팝업

### DSR API 임포트 규칙

DSR Python API는 ROS 환경에서만 로드 가능. `cobot1/motion/dsr_imports.py`의 `import_dsr_api()`를 통해서만 접근하고, 직접 `import DR_init` 하지 않는다.  
`PYTHONPATH`에 `~/ros2_ws/install/dsr_common2/lib/dsr_common2/imp` 가 없으면 import 실패.

### 상태 토픽 구조

`cobot1/status` 토픽 페이로드 (JSON):
```json
{"task": "open_bottle", "step": "probe_down", "state": "running", "message": "...", "timestamp": 1234567890.0}
```
- `state`: `running` / `done` / `error` / `stopped`
- `step == "finish"` + `state == "done"` → 태스크 정상 완료 (WebSocket sync 기준)

## 트러블슈팅 요점

| 증상 | 원인 |
|------|------|
| `No executable found` (care_web_api) | `source ~/ros2_ws/install/setup.bash` 후 재빌드 |
| `Set Robot Mode Service is not available` | bringup 미실행 또는 `ROS_DOMAIN_ID` 불일치 |
| 두 번째 태스크부터 실패 | `WebTaskSession` 세션 유지 버전인지 확인 (`care_web_api`) |
| bringup 인자 오류 | `mode:=real` 사용 (`model:=real` 아님) |
