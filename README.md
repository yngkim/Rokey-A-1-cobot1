# cobot1 — 침상 케어 로봇 (Doosan M0609)

노인·환자 보조를 위한 ROS 2 패키지입니다. Doosan **M0609** 협동로봇으로 음료·복약·스마트폰 충전 보조 동작을 수행하고, **모바일 웹 UI**로 원격 제어할 수 있습니다.

## 주요 기능 (4가지)

| 기능 | 명령 | 설명 |
|------|------|------|
| 페트병 뚜껑 열기 | `open_bottle` | 병 위 접근 → 뚜껑 잡기 → 단계적 비틀기 → 들어올리기 |
| 물 따르기 | `pour_water` | 페트병 집기 → 컵 위에서 기울여 따르기 → 병 복귀 |
| 알약 서랍에서 꺼내기 | `pick_place_pill` | 서랍 접근 → 알약 집기 → 지정 위치에 놓기 |
| 스마트폰 충전 | `place_on_charger` / `pick_from_charger` | 침상 ↔ 무선충전기에 놓기·가져오기 |

웹 UI에서는 위 4가지 기능이 **5개 버튼**(충전기 놓기/가져오기 분리)으로 표시됩니다.

### 안전·제어

- 동작 중 **외력 감지** 시 로봇 정지 + 웹 **주의 팝업**
- 실행 중 화면 **흐림 처리** + 하단 **실행 중 바** (단계 표시)
- **정지** 버튼으로 중간 취소 (`move_stop` + 안전 복귀)

---

## 사전 요구 사항

| 항목 | 버전/내용 |
|------|-----------|
| OS | Ubuntu 22.04 (Jammy) |
| ROS 2 | Humble |
| 로봇 | Doosan M0609 + Programming Manual V3.4.0 호환 |
| Doosan ROS 2 | `dsr_common2`, `dsr_msgs2`, `dsr_bringup2` 등 (워크스페이스에 별도 설치) |
| Python | 3.10+ |
| Node.js | 16+ (웹 UI 빌드용, `npm run build`) |

---

## 새 Linux PC에서 처음 설치하기

### 1. ROS 2 Humble 설치

[공식 문서](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debians.html)에 따라 설치 후:

```bash
echo 'export ROS_DOMAIN_ID=41' >> ~/.bashrc
echo 'source /opt/ros/humble/setup.bash' >> ~/.bashrc
source ~/.bashrc
```

> **중요:** bringup·태스크·웹 API **모든 터미널**에서 `ROS_DOMAIN_ID=41`이 동일해야 합니다.

### 2. 워크스페이스 준비

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
```

Doosan ROS 2 패키지(`dsr_common2`, `dsr_bringup2` 등)를 `src`에 클론/복사한 뒤, 이 저장소를 추가합니다.

```bash
git clone https://github.com/yngkim/Rokey-A-1-cobot1.git cobot1
```

### 3. 의존성 설치

```bash
cd ~/ros2_ws
rosdep install --from-paths src --ignore-src -r -y   # 가능한 경우

# 웹 API (FastAPI)
pip3 install --user -r ~/ros2_ws/src/cobot1/requirements-web.txt

# 웹 UI 빌드
cd ~/ros2_ws/src/cobot1/web
npm install
npm run build
```

### 4. 빌드

```bash
cd ~/ros2_ws
source /opt/ros/humble/setup.bash

# DSR Python API 경로 (bashrc에 추가 권장)
export PYTHONPATH=$PYTHONPATH:~/ros2_ws/install/dsr_common2/lib/dsr_common2/imp

colcon build --symlink-install
source install/setup.bash
```

`care_web_api` 실행 파일이 없으면 클린 빌드:

```bash
rm -rf build/cobot1 install/cobot1
colcon build --packages-select cobot1
source install/setup.bash
```

> `source`는 **`~/ros2_ws/install/setup.bash`** 를 사용하세요. `src/install`이 아닙니다.

### 5. 로봇 네트워크 (실기)

PC 유선 IP를 로봇과 같은 대역(`192.168.1.10`)으로 맞춥니다.

```bash
sudo ~/ros2_ws/src/cobot1/scripts/set_robot_network.sh
ping 192.168.1.100
```

팬던트에서 **SERVO ON**, 알람 해제 후 진행합니다.

---

## 실행 방법

### 터미널 1 — 로봇 bringup

```bash
~/ros2_ws/src/cobot1/scripts/run_bringup.sh
```

로그에 `Configured and activated dsr_controller2`가 보일 때까지 대기합니다.

### 터미널 2 — 웹 API + UI

```bash
~/ros2_ws/src/cobot1/scripts/run_care_web_api.sh
```

브라우저: **http://\<PC_IP\>:8080**

### 터미널에서 태스크만 단독 실행

```bash
source ~/ros2_ws/install/setup.bash
export PYTHONPATH=$PYTHONPATH:~/ros2_ws/install/dsr_common2/lib/dsr_common2/imp

ros2 run cobot1 open_bottle
ros2 run cobot1 pour_water
ros2 run cobot1 pick_place_pill
ros2 run cobot1 place_on_charger
ros2 run cobot1 pick_from_charger
```

### (선택) React 개발 서버

```bash
cd ~/ros2_ws/src/cobot1/web
npm run dev
# http://<PC_IP>:5173  (API는 8080으로 프록시)
```

---

## 설정

물체 좌표·속도·안전 한계는 `config/scenarios.yaml`에서 수정합니다. 실제 환경에 맞게 티칭한 pose로 바꿔 사용하세요.

```bash
# 예: 환경 변수로 다른 설정 파일 지정
export COBOT1_CONFIG=/path/to/my_scenarios.yaml
```

---

## 패키지 구조 (요약)

```
cobot1/
├── config/scenarios.yaml      # 좌표·동작 파라미터
├── cobot1/
│   ├── tasks/                 # 4대 핵심 태스크
│   ├── motion/                # 모션·안전·그리퍼
│   ├── bridge/                # FastAPI + 웹 브릿지
│   └── nodes/care_server.py   # (선택) ROS2 서비스 서버
├── web/                       # React 모바일 UI
└── scripts/                   # bringup·웹 API 실행 스크립트
```

---

## 트러블슈팅

| 증상 | 확인 |
|------|------|
| `No executable found` (care_web_api) | `source ~/ros2_ws/install/setup.bash` 후 재빌드 |
| `Set Robot Mode Service is not available` | bringup 완료 여부, `ROS_DOMAIN_ID=41` 통일 |
| 웹에 예전 버튼이 보임 | `care_web_api` 재시작 + 브라우저 강력 새로고침 |
| 두 번째 태스크부터 안 됨 | `care_web_api` 최신 버전 사용 (DSR 세션 유지) |

---

## 라이선스

Apache-2.0
