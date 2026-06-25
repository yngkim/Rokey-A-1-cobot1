
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  DEFAULT_TASKS,
  checkHealth,
  connectWebSocket,
  fetchTasks,
  resetRobot,
  stopTask,
  taskLabelById,
} from '../api/client'

function isTerminalStatus(data) {
  const state = data?.state
  const step = data?.step
  if (step === 'finish' && state === 'done') return true
  if (state === 'error' || state === 'stopped') return true
  if (
    (step === 'safe_abort' || step === 'user_stop') &&
    ['error', 'recovered', 'critical'].includes(state)
  ) {
    return true
  }
  return false
}

function shouldClearBusy(data, voiceChainActive) {
  if (!isTerminalStatus(data)) return false
  const state = data?.state
  const step = data?.step
  if (state === 'stopped' || state === 'error') return true
  if (
    (step === 'safe_abort' || step === 'user_stop') &&
    ['error', 'recovered', 'critical'].includes(state)
  ) {
    return true
  }
  if (step === 'finish' && state === 'done') return !voiceChainActive
  return !voiceChainActive
}

const VOICE_TASK_LABELS = {
  prepare_medication: '약 준비하기',
}

export function useRobotApp(speechRef) {
  const [tasks, setTasks] = useState(DEFAULT_TASKS)
  const [apiOnline, setApiOnline] = useState(false)
  const [robotReady, setRobotReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [activeTaskId, setActiveTaskId] = useState('')
  const [activeTaskLabel, setActiveTaskLabel] = useState('')
  const [status, setStatus] = useState(null)
  const [alert, setAlert] = useState(null)
  const [toast, setToast] = useState(null)
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
    clearBusy()
  }, [clearBusy, speechRef])

  const showToast = useCallback((message, level = 'info') => {
    setToast({ message, level, id: Date.now() })
    setTimeout(() => setToast(null), 4000)
  }, [])

  const applySync = useCallback((data) => {
    if (!data) return
    setBusy(!!data.busy)
    setActiveTaskId(data.current_task || '')
    if (data.last_status) setStatus(data.last_status)
    if (!data.busy) setStopping(false)
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
        setActiveTaskId(h.current_task || '')
        updateTaskLabel(h.current_task || '', h.current_task_label || '')
        if (!h.busy) {
          setStopping(false)
          voiceChainRef.current = false
        }
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
        setStopping(false)
        return
      }
      stopTimeoutRef.current = setTimeout(() => {
        clearBusy()
        refreshHealth()
        showToast('정지 처리가 지연되어 화면을 초기화했습니다', 'info')
      }, 90000)
    } catch (err) {
      showToast(err.message, 'error')
      setStopping(false)
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

  useEffect(() => {
    refreshHealth()

    const ws = connectWebSocket((msg) => {
      if (msg.type === 'sync') {
        applySync(msg.data)
        return
      }

      if (msg.type === 'task_complete') {
        const data = msg.data || {}
        voiceChainRef.current = false
        clearBusy()
        if (data.forced_idle) {
          showToast('화면 잠금을 해제했습니다', 'info')
          return
        }
        const speech = speechRef?.current
        if (data.voice_command_id) {
          if (data.success) {
            showToast('작업이 완료되었습니다')
            speech?.speakComplete?.(data.voice_command_id)
          } else {
            showToast('작업 중 오류가 발생했습니다', 'error')
            speech?.speakGlobal?.('error')
          }
          return
        }
        if (data.success) {
          showToast('작업이 완료되었습니다')
        }
        return
      }

      if (msg.type === 'status') {
        setStatus(msg.data)
        const state = msg.data?.state
        const step = msg.data?.step
        if (msg.data?.task) setActiveTaskId(msg.data.task)

        if (state === 'running') {
          setBusy(true)
          if (step !== 'user_stop') {
            setStopping(false)
          }
        }

        if (shouldClearBusy(msg.data, voiceChainRef.current)) {
          if (state === 'stopped' || state === 'error' || step === 'user_stop') {
            voiceChainRef.current = false
          }
          clearBusy()
          if (step === 'finish' && state === 'done') {
            showToast('작업이 완료되었습니다')
          }
          if (state === 'error') {
            showToast(msg.data.message || '오류 발생', 'error')
          }
          if (state === 'stopped') {
            showToast(msg.data.message || '작업이 중단되었습니다', 'info')
          }
          if (step === 'user_stop' && state === 'recovered') {
            showToast('정지 후 홈 복귀가 완료되었습니다', 'info')
          }
          return
        }

        if (state === 'stopping' || step === 'user_stop') setStopping(true)

        if (state === 'done' && step !== 'finish') {
          showToast(`${step} 완료`)
        }

        if (
          msg.data?.code === 'EXTERNAL_FORCE' ||
          msg.data?.step === 'safety_abort'
        ) {
          showSafetyAlert(msg.data)
        }
      }

      if (msg.type === 'safety_alert') {
        showSafetyAlert(msg.data)
      }
    })
    wsRef.current = ws

    const healthTimer = setInterval(refreshHealth, 2000)

    return () => {
      clearInterval(healthTimer)
      clearStopTimeout()
      ws.close()
    }
  }, [applySync, clearBusy, clearStopTimeout, refreshHealth, showSafetyAlert, showToast, speechRef])

  return {
    tasks,
    apiOnline,
    robotReady,
    busy,
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
    resetting,
    clearAlert: () => setAlert(null),
    markTaskStarted: (taskId) => {
      setBusy(true)
      setActiveTaskId(taskId)
      updateTaskLabel(taskId, VOICE_TASK_LABELS[taskId] || '')
      setStopping(false)
    },
    markVoiceChainStarted: (commandId) => {
      voiceChainRef.current = true
      setBusy(true)
      setActiveTaskId(commandId)
      updateTaskLabel(commandId, VOICE_TASK_LABELS[commandId] || '')
      setStopping(false)
    },
  }
}
