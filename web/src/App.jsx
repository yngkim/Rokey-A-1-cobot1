import { useState } from 'react'
import { runTask } from './api/client'
import SafetyAlertModal from './components/SafetyAlertModal'
import RunningDock from './components/RunningDock'
import { useRobotApp } from './hooks/useRobotApp'

function TaskButton({ task, disabled, hint, onRun }) {
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
      className={`task-btn ${task.id === 'go_home' ? 'task-btn-control' : ''} ${loading ? 'loading' : ''} ${disabled ? 'disabled' : ''}`}
      onClick={handleClick}
      disabled={disabled || loading}
      title={hint}
    >
      <span className="task-icon">{task.icon}</span>
      <span className="task-label">{task.label}</span>
      {loading && <span className="task-spinner" />}
    </button>
  )
}

function connectionLabel(apiOnline, robotReady) {
  if (!apiOnline) return { text: 'API 미연결', className: 'off' }
  if (!robotReady) return { text: '로봇 대기', className: 'warn' }
  return { text: '연결됨', className: 'on' }
}

export default function App() {
  const {
    tasks,
    apiOnline,
    robotReady,
    busy,
    stopping,
    resetting,
    activeTaskLabel,
    status,
    alert,
    toast,
    showToast,
    refreshHealth,
    handleStop,
    handleReset,
    clearAlert,
    markTaskStarted,
  } = useRobotApp()

  const conn = connectionLabel(apiOnline, robotReady)
  const canRun = apiOnline && robotReady && !busy

  const disabledHint = !apiOnline
    ? 'care_web_api를 실행하세요 (포트 8080)'
    : !robotReady
      ? 'bringup 실행 및 SERVO ON 후 사용 가능'
      : busy
        ? '다른 작업 실행 중'
        : ''

  const handleRun = async (taskId) => {
    try {
      const result = await runTask(taskId)
      if (result.success) {
        markTaskStarted(taskId)
        showToast(result.message || '작업을 시작했습니다')
        refreshHealth()
      } else {
        showToast(result.message || '실행 실패', 'error')
      }
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  const groups = [...new Set(tasks.map((t) => t.group))]

  return (
    <div className={`phone-shell ${busy ? 'is-busy' : ''}`}>
      <div className="phone-notch" />
      <header className="app-header">
        <div>
          <h1>침상 케어 로봇</h1>
          <p className="subtitle">M0609 원격 제어</p>
        </div>
        <div className={`conn-badge ${conn.className}`}>{conn.text}</div>
      </header>

      {!apiOnline && (
        <div className="info-banner">
          웹 API 서버가 꺼져 있습니다.
          <code>ros2 run cobot1 care_web_api</code>
        </div>
      )}

      {apiOnline && !robotReady && (
        <div className="info-banner warn">
          로봇 bringup을 실행하고 팬던트에서 SERVO ON 하세요.
        </div>
      )}

      {alert && (
        <SafetyAlertModal alert={alert} onClose={clearAlert} onReset={handleReset} resetting={resetting} />
      )}

      <main className={`app-main ${busy ? 'dimmed' : ''}`}>
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
                    disabled={!canRun}
                    hint={disabledHint}
                    onRun={handleRun}
                  />
                ))}
            </div>
          </section>
        ))}

        <section className="task-section">
          <h2>복구</h2>
          <div className="task-grid">
            <button
              className={`task-btn task-btn-reset ${resetting ? 'loading' : ''}`}
              onClick={handleReset}
              disabled={resetting}
              title="SAFE_STOP 해제 후 홈 위치로 복귀합니다"
            >
              <span className="task-icon">🔄</span>
              <span className="task-label">초기화 / 홈 복귀</span>
              {resetting && <span className="task-spinner" />}
            </button>
          </div>
        </section>
      </main>

      <footer className="status-bar">
        {!busy && <span>버튼을 눌러 기능을 실행하세요</span>}
        {busy && status && (
          <span className="status-muted">
            [{status.task}] {status.step}
          </span>
        )}
      </footer>

      <RunningDock
        busy={busy}
        taskLabel={activeTaskLabel}
        step={status?.step}
        stepMessage={status?.message}
        onStop={handleStop}
        stopping={stopping}
      />

      {toast && (
        <div className={`toast toast-${toast.level}`} key={toast.id}>
          {toast.message}
        </div>
      )}
    </div>
  )
}
