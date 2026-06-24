const ALERT_TITLES = {
  EXTERNAL_FORCE: '외력 감지 — 동작 중단',
  UNSAFE_ROBOT_STATE: '로봇 안전 정지',
  SAFETY_ABORT: '안전 감시 중단',
}

export default function SafetyAlertModal({ alert, onClose, onReset, resetting }) {
  if (!alert) return null

  const code = alert.code || ''
  const title = ALERT_TITLES[code] || '안전 주의'
  const isExternalForce = code === 'EXTERNAL_FORCE'
  const isSafeStop = code === 'UNSAFE_ROBOT_STATE' || code === 'SAFETY_ABORT'

  const handleReset = () => {
    if (onReset) onReset()
    onClose()
  }

  return (
    <div className="safety-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="safety-modal-title">
      <div className={`safety-modal ${isExternalForce ? 'safety-modal--force' : ''}`}>
        <div className="safety-modal-icon" aria-hidden="true">
          {isExternalForce ? '🛑' : '⚠️'}
        </div>
        <h2 id="safety-modal-title" className="safety-modal-title">
          {title}
        </h2>
        <p className="safety-modal-message">
          {alert.message || '로봇 동작이 안전을 위해 중단되었습니다.'}
        </p>
        {alert.task && (
          <p className="safety-modal-task">작업: {alert.task}</p>
        )}
        {isExternalForce && (
          <ul className="safety-modal-checklist">
            <li>환자·물체 접촉 여부를 확인하세요</li>
            <li>팬던트에서 알람을 해제하세요</li>
            <li>이상 없으면 다시 작업을 시작하세요</li>
          </ul>
        )}
        {isSafeStop && (
          <ul className="safety-modal-checklist">
            <li>로봇이 SAFE_STOP 상태입니다</li>
            <li>아래 초기화 버튼으로 상태를 해제할 수 있습니다</li>
          </ul>
        )}
        <div className="safety-modal-actions">
          {onReset && (
            <button
              type="button"
              className={`safety-modal-btn safety-modal-btn--reset ${resetting ? 'loading' : ''}`}
              onClick={handleReset}
              disabled={resetting}
            >
              {resetting ? '초기화 중...' : '🔄 초기화 / 홈 복귀'}
            </button>
          )}
          <button type="button" className="safety-modal-btn" onClick={onClose}>
            확인
          </button>
        </div>
      </div>
    </div>
  )
}
