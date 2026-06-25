const STEP_LABELS = {
  home: '홈 위치 이동',
  go_home: '홈 위치 이동',
  go_home_lift: 'Z 상승 (홈 복귀)',
  go_home_travel: '홈 방향 수평 이동',
  go_home_descend: 'Z 하강',
  go_home_align: '홈 조인트 정렬',
  home_finish_lift: 'Z 상승 (홈 복귀)',
  home_finish_travel: '홈 방향 수평 이동',
  home_finish_descend: 'Z 하강',
  home_finish_align: '홈 조인트 정렬',
  home_finish: '홈 복귀',
  approach: '접근 중',
  approach_bottle: '병 접근',
  descend_to_cap: '뚜껑 위치로 하강',
  move_search_start: '탐색 위치 이동',
  probe_down: '뚜껑 높이 탐색',
  align_cap_grasp: '뚜껑 잡기 위치',
  cap_grasped: '뚜껑 잡기',
  search_lift: '탐색 높이로 상승',
  move_cap_place: '뚜껑 내려놓기 이동',
  place_cap_down: '뚜껑 내려놓기',
  release_compliance: '순응 제어 해제',
  open_gripper: '그리퍼 열기',
  approach_drawer: '서랍 접근',
  approach_phone: '스마트폰 접근',
  approach_charger: '충전기 접근',
  approach_j5: 'J5 사전 정렬',
  approach_j4: 'J4 사전 정렬',
  approach_prepose: '거치대 접근 준비',
  move_charger_grasp: '핸드폰 파지 위치 이동',
  retract_prepose: '준비 포즈 후퇴',
  return_prepose: '준비 포즈 복귀',
  return_j4: 'J4 복귀',
  return_j5: 'J5 복귀',
  approach_bedside: '침상 접근',
  move_charger: '충전기 위치 이동',
  move_handoff: '인수인계 위치 이동',
  move_route_mid: '중간 경유 이동',
  move_route_mid_return: '중간 경유 복귀',
  move_route_mid_lift: 'Z 상승 (중간 경유)',
  move_route_mid_travel: '중간 경유 수평 이동',
  move_route_mid_descend: 'Z 하강 (중간 경유)',
  move_route_mid_return_lift: 'Z 상승 (중간 복귀)',
  move_route_mid_return_travel: '중간 복귀 수평 이동',
  move_route_mid_return_descend: 'Z 하강 (중간 복귀)',
  move_charger_align: '충전기 조인트 정렬',
  move_handoff_align: '인수인계 조인트 정렬',
  move_route_mid_align: '중간 경유 조인트 정렬',
  move_route_mid_return_align: '중간 복귀 조인트 정렬',
  move_charger_lift: 'Z 상승 (장애물 회피)',
  move_charger_travel: '수평 이동',
  move_charger_descend: 'Z 하강',
  move_handoff_lift: 'Z 상승 (장애물 회피)',
  move_handoff_travel: '수평 이동',
  move_handoff_descend: 'Z 하강',
  wait_handoff_release: '핸드폰 전달 대기',
  wait_handoff_grasp: '핸드폰 올려놓기 대기',
  approach_place: '놓는 위치 이동',
  approach_pick: '집기 위치 이동',
  grasp_bottle: '병 잡기',
  grasp_phone: '스마트폰 잡기',
  grip_phone: '핸드폰 파지',
  lift_after_grasp: '파지 후 수직 상승',
  release_phone: '핸드폰 놓기',
  grip_cap: '뚜껑 잡기',
  grip_pill: '알약 집기',
  twist_open: '뚜껑 돌리기',
  pour_tilt: '물병 기울이기',
  pour_tilt_fast: '빠르게 기울이기',
  pour_tilt_slow: '천천히 기울이기',
  untilt: '물병 세우기',
  untilt_fast: '빠르게 세우기',
  untilt_slow: '천천히 세우기',
  relax_grip: '약한 재파지',
  tilt_pour: '물 따르기',
  hold_pour: '따르는 중',
  home_lift: '홈 복귀 상승',
  home_travel: '홈 방향 이동',
  place_on_pad: '충전기에 놓기',
  user_stop: '정지 중',
  safe_abort: '안전 복귀',
  finish: '완료',
}

export function stepLabel(step) {
  if (!step) return '준비 중'
  return STEP_LABELS[step] || step.replace(/_/g, ' ')
}

export default function RunningDock({ busy, taskLabel, step, stepMessage, onStop, stopping }) {
  if (!busy) return null

  return (
    <>
      <div className="run-overlay" aria-hidden="true" />
      <div className="running-dock" role="status">
        <div className="running-dock-pulse" />
        <div className="running-dock-body">
          <div className="running-dock-info">
            <span className="running-dock-label">실행 중</span>
            <strong className="running-dock-task">{taskLabel || '작업'}</strong>
            <span className="running-dock-step">{stepLabel(step)}</span>
            {stepMessage && (
              <span className="running-dock-msg">{stepMessage}</span>
            )}
          </div>
          <button
            type="button"
            className="running-dock-stop"
            onClick={onStop}
            disabled={stopping}
          >
            {stopping ? '정지 중…' : '■ 정지'}
          </button>
        </div>
      </div>
    </>
  )
}
