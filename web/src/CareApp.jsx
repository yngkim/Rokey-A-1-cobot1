import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import {
  fetchActiveCareUser,
  fetchCareUsers,
  fetchVoiceCatalog,
  forceIdle,
  recordCareEvent,
  runTask,
  speechCommandIdForTask,
  sendHandoffConfirm,
  setActiveCareUser,
  taskVoiceHintsFromCatalog,
} from './api/client'
import CareMenuButton from './components/CareMenuButton'
import DeviceLayoutToggle from './components/DeviceLayoutToggle'
import SafetyAlertModal from './components/SafetyAlertModal'
import RunningDock from './components/RunningDock'
import TabletTaskGrid from './components/TabletTaskGrid'
import TaskButton from './components/TaskButton'
import VoiceButton from './components/VoiceButton'
import { useDeviceLayout } from './hooks/useDeviceLayout'
import { useRobotApp } from './hooks/useRobotApp'
import { useRobotSpeech } from './hooks/useRobotSpeech'
import { useVoiceInput } from './hooks/useVoiceInput'
import { useWakeWordListener } from './hooks/useWakeWordListener'
import MedicationSchedulePage from './pages/MedicationSchedulePage'
import { primeAudioSession } from './speech/audioPrime'

function phoneTaskHint(taskId, phoneLocation) {
  if (taskId === 'pick_from_charger' && phoneLocation === 'with_user') {
    return '핸드폰은 이미 가져가셨어요'
  }
  if (taskId === 'place_on_charger' && phoneLocation === 'on_charger') {
    return '핸드폰은 이미 거치대에 있어요'
  }
  return ''
}

function trayTaskHint(taskId, trayLocation) {
  if (
    (taskId === 'serve_meal' || taskId === 'return_tray') &&
    trayLocation !== 'on_station'
  ) {
    return '트레이가 원위치에 없습니다'
  }
  return ''
}

function connectionLabel(apiOnline, robotReady) {
  if (!apiOnline) return { text: 'API 미연결', className: 'off' }
  if (!robotReady) return { text: '로봇 대기', className: 'warn' }
  return { text: '연결됨', className: 'on' }
}

function InfoBanners({ apiOnline, maintenance, robotReady }) {
  if (!apiOnline) {
    return (
      <div className="info-banner">
        웹 API 서버가 꺼져 있습니다.
        <code>ros2 run cobot1 care_web_api</code>
      </div>
    )
  }
  if (maintenance) {
    return (
      <div className="info-banner warn">
        점검 중입니다. 잠시 후 다시 이용해 주세요.
      </div>
    )
  }
  if (!robotReady) {
    return (
      <div className="info-banner warn">
        로봇 bringup을 실행하고 팬던트에서 SERVO ON 하세요.
      </div>
    )
  }
  return null
}

export default function CareApp() {
  const speech = useRobotSpeech()
  const speechRef = useRef(speech)
  speechRef.current = speech

  const { layout, setLayout, isTablet } = useDeviceLayout()

  const [careUsers, setCareUsers] = useState([])
  const [activeUserId, setActiveUserId] = useState('')
  const [activeUserName, setActiveUserName] = useState('')
  const [taskVoiceHints, setTaskVoiceHints] = useState({})
  const [wakeWordConfig, setWakeWordConfig] = useState(null)
  const startListeningRef = useRef(null)

  const {
    tasks,
    apiOnline,
    robotReady,
    busy,
    maintenance,
    phoneLocation,
    trayLocation,
    handoffAction,
    handoffPrompt,
    stopping,
    resetting,
    safetyDeciding,
    activeTaskLabel,
    status,
    alert,
    toast,
    showToast,
    refreshHealth,
    handleStop,
    handleReset,
    handleSafetyDecision,
    clearAlert,
    markTaskStarted,
    markVoiceChainStarted,
  } = useRobotApp(speechRef)

  useEffect(() => {
    if (!apiOnline) return
    Promise.all([fetchCareUsers(), fetchActiveCareUser()])
      .then(([usersRes, activeRes]) => {
        setCareUsers(usersRes.users || [])
        const user = activeRes.user
        if (user) {
          setActiveUserId(user.id)
          setActiveUserName(user.name)
        }
      })
      .catch(() => {})
  }, [apiOnline])

  useEffect(() => {
    fetchVoiceCatalog()
      .then((data) => {
        setTaskVoiceHints(taskVoiceHintsFromCatalog(data))
        if (data?.wake_word) {
          setWakeWordConfig(data.wake_word)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (apiOnline && robotReady && !maintenance) {
      primeAudioSession().catch(() => {})
    }
  }, [apiOnline, robotReady, maintenance])

  const handleUserChange = async (userId) => {
    try {
      const result = await setActiveCareUser(userId)
      setActiveUserId(result.user.id)
      setActiveUserName(result.user.name)
      showToast(`${result.user.name} 사용자로 설정되었습니다`, 'info')
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  const handleCareLog = async (eventType, label) => {
    try {
      await recordCareEvent(eventType, { quantity: 1 })
      showToast(`${label} 기록되었습니다`, 'info')
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  const handleVoiceResult = useCallback(
    async (result, heardText) => {
      if (result.speech) {
        await speech.speakFromResponse(result.speech)
      }

      if (!result.matched) {
        const heard = heardText || result.heard_text || ''
        showToast(
          heard ? `인식: 「${heard}」 — 등록된 명령이 없습니다` : '인식된 명령이 없습니다',
          'info',
        )
        return
      }

      if (result.code === 'STARTED') {
        if (result.command_id === 'prepare_medication') {
          markVoiceChainStarted('prepare_medication')
        } else {
          markTaskStarted(result.task_id || result.command_id || '')
        }
        showToast(result.message || '작업을 시작했습니다')
        refreshHealth()
        return
      }

      if (
        result.code === 'PHONE_WITH_USER' ||
        result.code === 'PHONE_ON_CHARGER'
      ) {
        showToast(result.message || '지금은 실행할 수 없습니다', 'info')
        return
      }

      if (result.code === 'BUSY' || result.code === 'MAINTENANCE') {
        showToast(result.message || '다른 작업 실행 중', 'info')
        return
      }

      if (result.code === 'NOT_MATCHED') {
        return
      }

      if (!result.success) {
        showToast(result.message || '명령을 실행하지 못했습니다', 'error')
      }
    },
    [
      markTaskStarted,
      markVoiceChainStarted,
      refreshHealth,
      showToast,
      speech,
    ],
  )

  const handleVoiceError = useCallback(
    (message) => {
      showToast(message, 'error')
    },
    [showToast],
  )

  const wakePhrases = wakeWordConfig?.phrases || ['돌봄아', '돌봄 아']

  const voice = useVoiceInput({
    enabled: apiOnline && robotReady && !maintenance,
    busy,
    isSpeaking: speech.isSpeaking,
    wakePhrases,
    onResult: handleVoiceResult,
    onError: handleVoiceError,
  })

  startListeningRef.current = voice.startListening

  const handleWake = useCallback(
    async (response) => {
      await speech.speakText(response)
      await startListeningRef.current?.()
    },
    [speech],
  )

  const wakeListener = useWakeWordListener({
    enabled: apiOnline && robotReady && !maintenance,
    busy,
    maintenance,
    speaking: speech.speaking,
    commandActive: voice.isListening || voice.isProcessing,
    wakeConfig: wakeWordConfig,
    onWake: handleWake,
    onError: handleVoiceError,
  })

  const handleVoicePress = useCallback(async () => {
    wakeListener.stopAmbient()
    await voice.startListening()
  }, [voice, wakeListener])

  const conn = connectionLabel(apiOnline, robotReady)
  const canRun = apiOnline && robotReady && !busy && !maintenance
  const voiceDisabled =
    !apiOnline
    || !robotReady
    || busy
    || maintenance
    || voice.isProcessing
    || speech.speaking

  const disabledHint = maintenance
    ? '유지보수 모드 중입니다'
    : !apiOnline
      ? 'care_web_api를 실행하세요 (포트 8080)'
      : !robotReady
        ? 'bringup 실행 및 SERVO ON 후 사용 가능'
        : busy
          ? '다른 작업 실행 중'
          : ''

  const handleRun = async (taskId) => {
    try {
      const result = await runTask(taskId, activeUserId || null)
      if (result.success) {
        if (taskId === 'prepare_medication' || result.chain) {
          markVoiceChainStarted('prepare_medication')
        } else {
          markTaskStarted(taskId)
        }
        await primeAudioSession()
        await speech.speakAck(speechCommandIdForTask(taskId))
        showToast(result.message || '작업을 시작했습니다')
        refreshHealth()
      } else {
        showToast(result.message || '실행 실패', 'error')
        refreshHealth()
      }
    } catch (err) {
      showToast(err.message, 'error')
      refreshHealth()
    }
  }

  const handleHandoffConfirm = async (action) => {
    try {
      await sendHandoffConfirm(action)
      showToast('트레이 가져가기 확인', 'info')
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  const handleForceIdle = async () => {
    try {
      await forceIdle()
      showToast('화면 잠금을 해제했습니다', 'info')
      refreshHealth()
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  const groups = [...new Set(tasks.map((t) => t.group))]

  const shellClass = [
    'care-shell',
    isTablet ? 'layout-tablet' : 'layout-phone',
    busy ? 'is-busy' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={shellClass}>
      {!isTablet && <div className="phone-notch" />}

      <header className={`app-header ${isTablet ? 'app-header-tablet' : ''}`}>
        <div className="app-header-title">
          <h1>침상 케어 로봇</h1>
          <p className="subtitle">M0609 원격 제어</p>
        </div>
        <DeviceLayoutToggle layout={layout} onChange={setLayout} />
        <div className={`conn-badge ${conn.className}`}>{conn.text}</div>
      </header>

      {apiOnline && careUsers.length > 0 && (
        <div className={`care-user-bar ${isTablet ? 'care-user-bar-tablet' : ''}`}>
          <label htmlFor="care-user-select">사용자</label>
          <select
            id="care-user-select"
            value={activeUserId}
            onChange={(e) => handleUserChange(e.target.value)}
            disabled={busy}
          >
            {careUsers.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
          {activeUserName && <span className="care-user-hint">{activeUserName}님</span>}
        </div>
      )}

      <InfoBanners
        apiOnline={apiOnline}
        maintenance={maintenance}
        robotReady={robotReady}
      />

      {alert && (
        <SafetyAlertModal
          alert={alert}
          onClose={clearAlert}
          onReset={handleReset}
          onResume={() => handleSafetyDecision('resume')}
          onStopAndHome={() => handleSafetyDecision('home')}
          resetting={resetting}
          deciding={safetyDeciding}
        />
      )}

      <Routes>
        <Route
          index
          element={
            <>
              {isTablet ? (
                <div className="tablet-toolbar">
                  <VoiceButton
                    compact
                    supported={voice.supported}
                    disabled={voiceDisabled}
                    isListening={voice.isListening}
                    isProcessing={voice.isProcessing}
                    isAmbient={wakeListener.isAmbient}
                    interimText={voice.interimText}
                    onPress={handleVoicePress}
                  />
                  <Link to="/medication-schedule" className="tablet-menu-link">
                    ⏰ 약 복용 시간
                  </Link>
                </div>
              ) : (
                <VoiceButton
                  supported={voice.supported}
                  disabled={voiceDisabled}
                  isListening={voice.isListening}
                  isProcessing={voice.isProcessing}
                  isAmbient={wakeListener.isAmbient}
                  interimText={voice.interimText}
                  onPress={handleVoicePress}
                />
              )}

              <main className={`app-main ${busy ? 'dimmed' : ''} ${isTablet ? 'app-main-tablet' : ''}`}>
                {isTablet ? (
                  <TabletTaskGrid
                    tasks={tasks}
                    canRun={canRun}
                    disabledHint={disabledHint}
                    phoneLocation={phoneLocation}
                    trayLocation={trayLocation}
                    taskVoiceHints={taskVoiceHints}
                    activeUserId={activeUserId}
                    onRun={handleRun}
                    onCareLog={handleCareLog}
                  />
                ) : (
                  <>
                    {groups.map((group) => (
                      <section key={group} className="task-section">
                        <h2>{group}</h2>
                        <div className="task-grid">
                          {tasks
                            .filter((t) => t.group === group)
                            .map((task) => {
                              const phoneHint = phoneTaskHint(task.id, phoneLocation)
                              const trayHint = trayTaskHint(task.id, trayLocation)
                              const taskHint = phoneHint || trayHint
                              return (
                                <TaskButton
                                  key={task.id}
                                  task={task}
                                  disabled={!canRun || !!taskHint}
                                  hint={taskHint || disabledHint}
                                  voiceHints={taskVoiceHints}
                                  onRun={handleRun}
                                />
                              )
                            })}
                        </div>
                      </section>
                    ))}

                    <section className="task-section">
                      <h2>기능</h2>
                      <div className="task-grid">
                        <CareMenuButton
                          to="/medication-schedule"
                          icon="⏰"
                          label="약 복용 시간"
                          hint="자동 약 준비 설정"
                          disabled={!apiOnline || !activeUserId}
                        />
                      </div>
                    </section>

                    <section className="task-section">
                      <h2>복약 기록</h2>
                      <div className="task-grid">
                        <button
                          type="button"
                          className="task-btn"
                          disabled={!canRun || !activeUserId}
                          onClick={() => handleCareLog('medication_taken', '복용 완료')}
                          title={disabledHint || '복용 완료 기록'}
                        >
                          <span className="task-icon">✅</span>
                          <span className="task-label">복용 완료</span>
                        </button>
                      </div>
                    </section>
                  </>
                )}
              </main>
            </>
          }
        />
        <Route
          path="medication-schedule"
          element={
            <MedicationSchedulePage
              userId={activeUserId}
              userName={activeUserName}
              busy={busy}
              isTablet={isTablet}
              onToast={showToast}
            />
          }
        />
      </Routes>

      <footer className={`status-bar ${isTablet ? 'status-bar-tablet' : ''}`}>
        {!busy && <span>버튼 또는 음성으로 기능을 실행하세요</span>}
        {busy && (
          <>
            <span className="status-muted">
              {status ? `[${status.task}] ${status.step}` : '실행 중…'}
            </span>
            <button type="button" className="force-idle-btn" onClick={handleForceIdle}>
              화면 잠금 해제
            </button>
          </>
        )}
        <Link to="/admin" className="admin-footer-link">
          관리자
        </Link>
      </footer>

      <RunningDock
        busy={busy}
        taskLabel={activeTaskLabel}
        step={status?.step}
        stepMessage={status?.message || handoffPrompt}
        handoffAction={handoffAction}
        onHandoffConfirm={handleHandoffConfirm}
        onStop={handleStop}
        stopping={stopping}
        layout={isTablet ? 'tablet' : 'phone'}
      />

      {toast && (
        <div className={`toast toast-${toast.level}`} key={toast.id}>
          {toast.message}
        </div>
      )}
    </div>
  )
}
