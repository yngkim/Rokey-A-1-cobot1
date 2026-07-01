
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  DEFAULT_TASKS,
  checkHealth,
  connectWebSocket,
  fetchTasks,
  forceIdle,
  resetRobot,
  sendSafetyDecision,
  speechCommandIdForTask,
  stopTask,
  taskLabelById,
} from '../api/client'

const OBJECT_MISSING_MESSAGE = '대상 물건이 없습니다. 다시 확인해 주세요.'

function shouldShowStatusToast(data, voiceChainActive) {
  const state = data?.state
  const step = data?.step
  if (data?.code === 'OBJECT_MISSING') return false
  if (step === 'finish' && state === 'done') return !voiceChainActive
  if (state === 'error' && step !== 'user_stop' && step !== 'safe_abort') return true
  if (step === 'user_stop' && state === 'recovered') return true
  return false
}

/** sync/health의 safety_decision_pending으로 외력 팝업 표시·해제 */
function syncSafetyAlertFromGate(setAlert, data) {
  if (data?.safety_decision_pending) {
    setAlert({
      code: 'EXTERNAL_FORCE',
      message:
        data.safety_pause_message ||
        '로봇 동작이 안전을 위해 중단되었습니다. 주변을 확인해 주세요.',
      task: data.safety_pause_task || '',
      timestamp: Date.now(),
    })
    return
  }
  setAlert((prev) => (prev?.code === 'EXTERNAL_FORCE' ? null : prev))
}

const VOICE_TASK_LABELS = {
  prepare_medication: '약 준비하기',
  clean_floor: '청소하기',
  serve_meal: '식사 가져오기',
  return_tray: '식사 가져가기',
}

export function useRobotApp(speechRef) {
  const [tasks, setTasks] = useState(DEFAULT_TASKS)
  const [apiOnline, setApiOnline] = useState(false)
  const [robotReady, setRobotReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const [maintenance, setMaintenance] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [safetyDeciding, setSafetyDeciding] = useState(false)
  const [activeTaskId, setActiveTaskId] = useState('')
  const [activeTaskLabel, setActiveTaskLabel] = useState('')
  const [status, setStatus] = useState(null)
  const [alert, setAlert] = useState(null)
  const [toast, setToast] = useState(null)
  const [phoneLocation, setPhoneLocation] = useState('on_charger')
  const [trayLocation, setTrayLocation] = useState('on_station')
  const [handoffAction, setHandoffAction] = useState(null)
  const [handoffPrompt, setHandoffPrompt] = useState('')
  const wsRef = useRef(null)
  const voiceChainRef = useRef(false)
  const stopTimeoutRef = useRef(null)

  const clearStopTimeout = useCallback(() => {
    if (stopTimeoutRef.current) {
      clearTimeout(stopTimeoutRef.current)
      stopTimeoutRef.current = null
    }
  }, [])

  const clearBusy = useCallback(() => {
    clearStopTimeout()
    setBusy(false)
    setStopping(false)
    setResetting(false)
    setActiveTaskId('')
    voiceChainRef.current = false
    setHandoffAction(null)
    setHandoffPrompt('')
  }, [clearStopTimeout])

  const showSafetyAlert = useCallback((data) => {
    speechRef?.current?.cancelSpeech?.()
    speechRef?.current?.speakGlobal?.('error')
    setAlert({
      code: data?.code || '',
      message: data?.message || data?.user_message || '안전 경고가 발생했습니다.',
      task: data?.task || '',
      detail: data?.detail || null,
      timestamp: data?.timestamp || Date.now(),
    })
    if (data?.code !== 'EXTERNAL_FORCE') {
      clearBusy()
    }
  }, [clearBusy, speechRef])

  const showObjectMissingAlert = useCallback((data) => {
    const message = data?.message || data?.speech_text || OBJECT_MISSING_MESSAGE
    speechRef?.current?.cancelSpeech?.()
    speechRef?.current?.speakText?.(message)
    setAlert({
      code: 'OBJECT_MISSING',
      message,
      objectLabel: data?.object_label || '',
      task: data?.task || '',
      timestamp: Date.now(),
    })
  }, [speechRef])

  const showToast = useCallback((message, level = 'info') => {
    setToast({ message, level, id: Date.now() })
    setTimeout(() => setToast(null), 4000)
  }, [])

  const applySync = useCallback((data) => {
    if (!data) return
    setBusy(!!data.busy)
    setMaintenance(!!data.maintenance)
    setActiveTaskId(data.current_task || '')
    if (data.phone_location) setPhoneLocation(data.phone_location)
    if (data.tray_location) setTrayLocation(data.tray_location)
    setHandoffAction(data.handoff_action || null)
    setHandoffPrompt(data.handoff_prompt || '')
    if (data.last_status) setStatus(data.last_status)
    if (!data.busy) {
      setStopping(false)
      setResetting(false)
      voiceChainRef.current = false
    }
    syncSafetyAlertFromGate(setAlert, data)
  }, [])

  const updateTaskLabel = useCallback((taskId, labelFromHealth) => {
    if (labelFromHealth) {
      setActiveTaskLabel(labelFromHealth)
      return
    }
    setActiveTaskLabel(VOICE_TASK_LABELS[taskId] || taskLabelById(tasks, taskId))
  }, [tasks])

  const refreshHealth = useCallback(() => {
    return checkHealth()
      .then((h) => {
        setApiOnline(!!h.api_ok)
        setRobotReady(!!h.robot_ready)
        setBusy(!!h.busy)
        setMaintenance(!!h.maintenance)
        setActiveTaskId(h.current_task || '')
        updateTaskLabel(h.current_task || '', h.current_task_label || '')
        if (h.phone_location) setPhoneLocation(h.phone_location)
        if (h.tray_location) setTrayLocation(h.tray_location)
        setHandoffAction(h.handoff_action || null)
        setHandoffPrompt(h.handoff_prompt || '')
        if (!h.busy) {
          setStopping(false)
          voiceChainRef.current = false
        }
        syncSafetyAlertFromGate(setAlert, h)
        return h
      })
      .catch(() => {
        setApiOnline(false)
        setRobotReady(false)
        return null
      })
  }, [updateTaskLabel])

  useEffect(() => {
    fetchTasks()
      .then((data) => {
        if (Array.isArray(data?.tasks) && data.tasks.length > 0) {
          setTasks(data.tasks)
        }
      })
      .catch(() => {})
  }, [])

  const handleStop = useCallback(async () => {
    if (stopping) return
    setStopping(true)
    clearStopTimeout()
    try {
      const result = await stopTask()
      showToast(result.message || '정지 요청을 보냈습니다', 'info')
      if (!result.success) {
        const h = await refreshHealth()
        if (h && !h.busy) {
          clearBusy()
        } else {
          setStopping(false)
        }
        return
      }
      stopTimeoutRef.current = setTimeout(async () => {
        try {
          await forceIdle()
        } catch {
          /* ignore — still refresh below */
        }
        clearBusy()
        refreshHealth()
        showToast('정지 처리가 지연되어 화면을 초기화했습니다', 'info')
      }, 30000)
    } catch (err) {
      showToast(err.message, 'error')
      setStopping(false)
      refreshHealth()
    }
  }, [clearBusy, clearStopTimeout, refreshHealth, showToast, stopping])

  const handleReset = useCallback(async () => {
    if (resetting) return
    setResetting(true)
    try {
      const result = await resetRobot()
      showToast(result.message || 'SAFE_STOP 해제 후 홈 복귀 중...', 'info')
      setBusy(true)
      setActiveTaskId('go_home')
    } catch (err) {
      showToast(err.message || '초기화 실패', 'error')
      setResetting(false)
    }
  }, [resetting, showToast])

  const handleSafetyDecision = useCallback(async (action) => {
    if (safetyDeciding) return
    setSafetyDeciding(true)
    try {
      const result = await sendSafetyDecision(action)
      setAlert(null)
      if (action === 'resume') {
        showToast(result.message || '작업을 재개합니다', 'info')
      } else {
        showToast(result.message || '작업을 중지하고 홈으로 복귀합니다', 'info')
      }
    } catch (err) {
      showToast(err.message || '선택 반영 실패', 'error')
    } finally {
      setSafetyDeciding(false)
    }
  }, [safetyDeciding, showToast])

  const markTaskStarted = useCallback((taskId) => {
    setBusy(true)
    setActiveTaskId(taskId)
    updateTaskLabel(taskId, VOICE_TASK_LABELS[taskId] || '')
    setStopping(false)
  }, [updateTaskLabel])

  const markVoiceChainStarted = useCallback((commandId) => {
    voiceChainRef.current = true
    setBusy(true)
    setActiveTaskId(commandId)
    updateTaskLabel(commandId, VOICE_TASK_LABELS[commandId] || '')
    setStopping(false)
  }, [updateTaskLabel])

  useEffect(() => {
    refreshHealth()

    const ws = connectWebSocket((msg) => {
      if (msg.type === 'sync') {
        applySync(msg.data)
        return
      }

      if (msg.type === 'maintenance') {
        setMaintenance(!!msg.data?.enabled)
        return
      }

      if (msg.type === 'object_missing') {
        showObjectMissingAlert(msg.data)
        return
      }

      if (msg.type === 'speech') {
        const text = msg.data?.text
        if (text) {
          speechRef?.current?.speakText?.(text)
        }
        return
      }

      if (msg.type === 'medication_auto') {
        const data = msg.data || {}
        if (data.success) {
          markVoiceChainStarted('prepare_medication')
          showToast(data.message || '약 시간에 맞춰 약 준비를 시작했습니다')
        } else if (data.message) {
          showToast(data.message, 'info')
        }
        refreshHealth()
        return
      }

      if (msg.type === 'task_complete') {
        const data = msg.data || {}
        voiceChainRef.current = false
        clearBusy()
        refreshHealth()
        if (data.forced_idle) {
          showToast('화면 잠금을 해제했습니다', 'info')
          return
        }
        const speech = speechRef?.current
        if (data.voice_command_id) {
          if (data.success) {
            showToast('작업이 완료되었습니다')
            speech?.speakComplete?.(data.voice_command_id)
          } else if (data.code === 'OBJECT_MISSING') {
            /* 팝업·TTS는 object_missing 이벤트에서 처리 */
          } else {
            showToast('작업 중 오류가 발생했습니다', 'error')
            speech?.speakGlobal?.('error')
          }
          return
        }
        const speechId = speechCommandIdForTask(data.task)
        if (data.success) {
          showToast('작업이 완료되었습니다')
          if (speechId) {
            speech?.speakComplete?.(speechId)
          }
        } else if (data.code === 'OBJECT_MISSING') {
          /* 팝업·TTS는 object_missing 이벤트에서 처리 */
        } else {
          showToast('작업 중 오류가 발생했습니다', 'error')
          speech?.speakGlobal?.('error')
        }
        return
      }

      if (msg.type === 'status') {
        setStatus(msg.data)
        const state = msg.data?.state
        const step = msg.data?.step
        if (msg.data?.task) setActiveTaskId(msg.data.task)

        if (shouldShowStatusToast(msg.data, voiceChainRef.current)) {
          if (step === 'finish' && state === 'done') {
            showToast('작업이 완료되었습니다')
          }
          if (state === 'error') {
            showToast(msg.data.message || '오류 발생', 'error')
          }
          if (step === 'user_stop' && state === 'recovered') {
            showToast('정지 후 홈 복귀가 완료되었습니다', 'info')
          }
        }

        if (state === 'stopping' || (step === 'user_stop' && state === 'running')) {
          setStopping(true)
        }

        if (msg.data?.code === 'OBJECT_MISSING') {
          showObjectMissingAlert(msg.data)
        }

        if (step === 'safety_abort' && state === 'error') {
          showSafetyAlert(msg.data)
        }
      }

      if (msg.type === 'safety_alert') {
        if (msg.data?.code !== 'EXTERNAL_FORCE') {
          showSafetyAlert(msg.data)
        }
      }
    })
    wsRef.current = ws

    const healthTimer = setInterval(refreshHealth, 2000)

    return () => {
      clearInterval(healthTimer)
      clearStopTimeout()
      ws.close()
    }
  }, [applySync, clearBusy, clearStopTimeout, markVoiceChainStarted, refreshHealth, showObjectMissingAlert, showSafetyAlert, showToast, speechRef])

  return {
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
    activeTaskId,
    activeTaskLabel,
    status,
    alert,
    toast,
    showToast,
    refreshHealth,
    handleStop,
    handleReset,
    handleSafetyDecision,
    resetting,
    safetyDeciding,
    clearAlert: () => setAlert(null),
    markTaskStarted,
    markVoiceChainStarted,
  }
}
