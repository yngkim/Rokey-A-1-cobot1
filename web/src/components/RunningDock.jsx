const STEP_LABELS = {
  home: '홈 위치 이동',
  go_home: '홈 위치 이동',
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
  approach_bedside: '침상 접근',
  approach_place: '놓는 위치 이동',
  approach_pick: '집기 위치 이동',
  grasp_bottle: '병 잡기',
  grasp_phone: '스마트폰 잡기',
  grip_cap: '뚜껑 잡기',
  grip_pill: '알약 집기',
  twist_open: '뚜껑 돌리기',
  tilt_pour: '물 따르기',
  hold_pour: '따르는 중',
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
