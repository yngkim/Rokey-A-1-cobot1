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
  move_charger_grasp_advance: 'TCP Z 미세 접근',
  move_charger_front: '거치대 앞 이동',
  move_charger_place: '거치대 놓기 이동',
  retract_prepose: '준비 포즈 후퇴',
  return_prepose: '준비 포즈 복귀',
  return_j4: 'J4 복귀',
  return_j5: 'J5 복귀',
  approach_bedside: '침상 접근',
  move_charger: '충전기 위치 이동',
  move_handoff: '인수인계 위치 이동',
  move_route_mid: '중간 경유 (조인트)',
  post_grasp_lift: '파지 후 Z 상승',
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
  move_handoff_travel: '인계 수평 이동',
  move_handoff_descend: '인계 Z 하강',
  wait_handoff_release: '핸드폰 전달 대기',
  wait_handoff_grasp: '핸드폰 올려놓기 대기',
  wait_user_gripper_open: '그리퍼 열기 대기',
  wait_user_gripper_close: '그리퍼 닫기 대기',
  wait_user_confirm_tray_return: '트레이 가져가기 대기',
  move_tray_grasp: '트레이 위치 이동',
  move_tray_grasp_elevated: '원위치 상공 이동',
  move_tray_grasp_descend: '원위치 Z 하강',
  grasp_tray: '트레이 파지',
  tray_weigh_before: '식전 무게 측정',
  tray_weigh_after: '식후 무게 측정',
  carry_to_user: '사용자에게 이송',
  carry_to_station: '원위치로 이송',
  handoff_tray_return: '트레이 인계',
  release_tray: '트레이 놓기',
  meal_intake: '식사량 계산',
  approach_place: '놓는 위치 이동',
  approach_pick: '집기 위치 이동',
  grasp_bottle: '병 잡기',
  grasp_phone: '스마트폰 잡기',
  grip_phone: '핸드폰 파지',
  confirm_phone_grasp: '핸드폰 파지 확인',
  lift_after_grasp: '파지 후 수직 상승',
  release_phone: '핸드폰 놓기',
  grip_cap: '뚜껑 잡기',
  grip_pill: '알약 집기',
  twist_open: '뚜껑 돌리기',
  soft_release_cap: '뚜껑 살살 놓기',
  preseat_lift: '사전 정렬 상승',
  close_empty_gripper: '빈 그리퍼 닫기',
  press_cap_center: '뚜껑 중앙 누르기',
  press_approach: '누르기 접근',
  open_for_regrasp: '재파지 준비 (열기)',
  descend_for_screw: '조임 위치 하강',
  regrasp_for_screw: '조임용 재파지',
  screw_j6_unwind: 'J6 각도 복원',
  screw_close: '뚜껑 조임',
  screw_close_extra: '추가 조임',
  carry_cap_to_screw: '조임 위치 이동',
  grasp_settle: '파지 완료 대기',
  regrasp_for_carry: '이송용 재파지',
  pour_tilt: '물병 기울이기',
  pre_rotate_j6: 'J6 사전 회전',
  align_body_grasp: '몸통 파지 조인트 정렬',
  align_cup_joints: '컵 옆 조인트 정렬',
  restore_j6_at_home: 'J6 복원',
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
  safety_pause: '외력 감지 — 대기',
  safe_abort: '안전 복귀',
  finish: '완료',
}

export function stepLabel(step) {
  if (!step) return '준비 중'
  return STEP_LABELS[step] || step.replace(/_/g, ' ')
}

export default function RunningDock({
  busy,
  taskLabel,
  step,
  stepMessage,
  handoffAction,
  onHandoffConfirm,
  onStop,
  stopping,
}) {
  if (!busy) return null

  const handoffLabel =
    handoffAction === 'tray_return' ? '트레이 가져가기' : null

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
          <div className="running-dock-actions">
            {handoffLabel && onHandoffConfirm && (
              <button
                type="button"
                className="running-dock-handoff"
                onClick={() => onHandoffConfirm(handoffAction)}
              >
                {handoffLabel}
              </button>
            )}
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
      </div>
    </>
  )
}
