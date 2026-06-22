const ALERT_TITLES = {
  EXTERNAL_FORCE: '외력 감지 — 동작 중단',
  UNSAFE_ROBOT_STATE: '로봇 안전 정지',
  SAFETY_ABORT: '안전 감시 중단',
}

export default function SafetyAlertModal({ alert, onClose }) {
  if (!alert) return null

  const code = alert.code || ''
  const title = ALERT_TITLES[code] || '안전 주의'
  const isExternalForce = code === 'EXTERNAL_FORCE'

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
        <button type="button" className="safety-modal-btn" onClick={onClose}>
          확인
        </button>
      </div>
    </div>
  )
}
