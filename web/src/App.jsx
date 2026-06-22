import { useState } from 'react'
import { runTask } from './api/client'
import { useRobotApp } from './hooks/useRobotApp'

function TaskButton({ task, disabled, onRun }) {
  const [loading, setLoading] = useState(false)

  const handleClick = async () => {
    if (disabled || loading) return
    setLoading(true)
    try {
      await onRun(task.id)
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      className={`task-btn ${loading ? 'loading' : ''}`}
      onClick={handleClick}
      disabled={disabled || loading}
    >
      <span className="task-icon">{task.icon}</span>
      <span className="task-label">{task.label}</span>
      {loading && <span className="task-spinner" />}
    </button>
  )
}

export default function App() {
  const { tasks, connected, busy, status, alert, toast, showToast, clearAlert } = useRobotApp()

  const handleRun = async (taskId) => {
    try {
      const result = await runTask(taskId)
      if (result.success) {
        showToast(result.message || '작업을 시작했습니다')
      } else {
        showToast(result.message || '실행 실패', 'error')
      }
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  const groups = [...new Set(tasks.map((t) => t.group))]

  return (
    <div className="phone-shell">
      <div className="phone-notch" />
      <header className="app-header">
        <div>
          <h1>침상 케어 로봇</h1>
          <p className="subtitle">M0609 원격 제어</p>
        </div>
        <div className={`conn-badge ${connected ? 'on' : 'off'}`}>
          {connected ? '연결됨' : '미연결'}
        </div>
      </header>

      {alert && (
        <div className="alert-banner" role="alert">
          <strong>⚠️ 안전 경고</strong>
          <p>{alert.message}</p>
          <button onClick={clearAlert}>확인</button>
        </div>
      )}

      <main className="app-main">
        {groups.map((group) => (
          <section key={group} className="task-section">
            <h2>{group}</h2>
            <div className="task-grid">
              {tasks
                .filter((t) => t.group === group)
                .map((task) => (
                  <TaskButton
                    key={task.id}
                    task={task}
                    disabled={!connected || busy}
                    onRun={handleRun}
                  />
                ))}
            </div>
          </section>
        ))}
      </main>

      <footer className="status-bar">
        {busy && <span className="status-busy">● 작업 실행 중...</span>}
        {status && (
          <span>
            [{status.task}] {status.step} — {status.state}
            {status.message ? `: ${status.message}` : ''}
          </span>
        )}
        {!status && !busy && <span>버튼을 눌러 기능을 실행하세요</span>}
      </footer>

      {toast && (
        <div className={`toast toast-${toast.level}`} key={toast.id}>
          {toast.message}
        </div>
      )}
    </div>
  )
}
