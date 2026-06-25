import { useState } from 'react'
import { adminForceIdle, adminReset, adminStop, setMaintenance } from '../../api/adminClient'

export default function ControlPanel({ maintenance, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const run = async (label, fn) => {
    setBusy(true)
    setMessage('')
    try {
      const result = await fn()
      setMessage(result.message || `${label} 완료`)
      onChanged?.()
    } catch (err) {
      setMessage(err.message || `${label} 실패`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="admin-panel">
      <h3>시스템 제어</h3>
      <div className="admin-controls">
        <button type="button" className="admin-btn danger" disabled={busy} onClick={() => run('정지', adminStop)}>
          정지
        </button>
        <button type="button" className="admin-btn warn" disabled={busy} onClick={() => run('리셋/홈', adminReset)}>
          SAFE_STOP 해제 + 홈
        </button>
        <button type="button" className="admin-btn" disabled={busy} onClick={() => run('잠금 해제', adminForceIdle)}>
          화면 잠금 해제
        </button>
        <button
          type="button"
          className={`admin-btn ${maintenance ? 'primary' : 'warn'}`}
          disabled={busy}
          onClick={() => run('유지보수', () => setMaintenance(!maintenance))}
        >
          유지보수 {maintenance ? 'OFF' : 'ON'}
        </button>
      </div>
      {message && <p style={{ marginTop: 10, fontSize: '0.88rem', color: '#9aa8bc' }}>{message}</p>}
    </div>
  )
}
