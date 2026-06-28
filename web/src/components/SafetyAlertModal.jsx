const ALERT_TITLES = {
  EXTERNAL_FORCE: '외력 감지 — 동작 중단',
  UNSAFE_ROBOT_STATE: '로봇 안전 정지',
  SAFETY_ABORT: '안전 감시 중단',
  OBJECT_MISSING: '물건 없음',
}

export default function SafetyAlertModal({
  alert,
  onClose,
  onReset,
  onResume,
  onStopAndHome,
  resetting,
  deciding,
}) {
  if (!alert) return null

  const code = alert.code || ''
  const title = ALERT_TITLES[code] || '안전 주의'
  const isExternalForce = code === 'EXTERNAL_FORCE'
  const isObjectMissing = code === 'OBJECT_MISSING'
  const isSafeStop = code === 'UNSAFE_ROBOT_STATE' || code === 'SAFETY_ABORT'

  const handleReset = () => {
    if (onReset) onReset()
    onClose()
  }

  return (
    <div className="safety-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="safety-modal-title">
      <div className={`safety-modal ${isExternalForce ? 'safety-modal--force' : ''} ${isObjectMissing ? 'safety-modal--missing' : ''}`}>
        <div className="safety-modal-icon" aria-hidden="true">
          {isExternalForce ? '🛑' : isObjectMissing ? '📦' : '⚠️'}
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
        {isObjectMissing && alert.objectLabel && (
          <p className="safety-modal-task">대상: {alert.objectLabel}</p>
        )}
        {isObjectMissing && (
          <ul className="safety-modal-checklist">
            <li>물건이 제자리에 있는지 확인하세요</li>
            <li>확인 후 다시 실행해 주세요</li>
          </ul>
        )}
        {isExternalForce && (
          <ul className="safety-modal-checklist">
            <li>로봇 주변을 확인하세요</li>
            <li>환자·물체 접촉 여부를 확인하세요</li>
            <li>이상 없으면 「작업 계속하기」를 눌러 주세요</li>
          </ul>
        )}
        {isSafeStop && (
          <ul className="safety-modal-checklist">
            <li>로봇이 SAFE_STOP 상태입니다</li>
            <li>아래 초기화 버튼으로 상태를 해제할 수 있습니다</li>
          </ul>
        )}
        <div className="safety-modal-actions">
          {isExternalForce ? (
            <>
              <button
                type="button"
                className={`safety-modal-btn safety-modal-btn--primary ${deciding ? 'loading' : ''}`}
                onClick={onResume}
                disabled={deciding}
              >
                {deciding ? '처리 중…' : '작업 계속하기'}
              </button>
              <button
                type="button"
                className={`safety-modal-btn safety-modal-btn--reset ${deciding ? 'loading' : ''}`}
                onClick={onStopAndHome}
                disabled={deciding}
              >
                {deciding ? '처리 중…' : '작업 중지하고 홈 복귀'}
              </button>
            </>
          ) : (
            <>
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
            </>
          )}
        </div>
      </div>
    </div>
  )
}
