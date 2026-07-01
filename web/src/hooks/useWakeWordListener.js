import { useCallback, useEffect, useRef, useState } from 'react'
import { ensureMicrophoneAccess, primeAudioSession } from '../speech/audioPrime'

function getSpeechRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

function normalizeWakeText(text) {
  return text.replace(/\s+/g, '').toLowerCase()
}

function containsWakeWord(text, phrases) {
  const normalized = normalizeWakeText(text)
  if (!normalized) return false
  return phrases.some((phrase) => normalized.includes(normalizeWakeText(phrase)))
}

const DEFAULT_WAKE = {
  phrases: ['돌봄아', '돌봄 아'],
  response: '네. 말씀하세요.',
}

const RESTART_DELAY_MS = 1200
const MIN_RESTART_GAP_MS = 1500

function detachRecognition(recognition) {
  if (!recognition) return
  try {
    recognition.onend = null
    recognition.onresult = null
    recognition.onerror = null
    recognition.stop()
  } catch {
    // already stopped
  }
}

export function useWakeWordListener({
  enabled,
  busy,
  maintenance,
  speaking,
  commandActive,
  wakeConfig,
  onWake,
  onError,
}) {
  const [isAmbient, setIsAmbient] = useState(false)
  const recognitionRef = useRef(null)
  const activeRef = useRef(false)
  const startingRef = useRef(false)
  const restartTimerRef = useRef(null)
  const lastStartAtRef = useRef(0)
  const wakeConfigRef = useRef(DEFAULT_WAKE)
  const onWakeRef = useRef(onWake)
  const onErrorRef = useRef(onError)

  const supported = typeof window !== 'undefined' && !!getSpeechRecognition()

  const propsRef = useRef({
    enabled,
    busy,
    maintenance,
    speaking,
    commandActive,
  })
  propsRef.current = {
    enabled,
    busy,
    maintenance,
    speaking,
    commandActive,
  }

  useEffect(() => {
    wakeConfigRef.current = {
      phrases: wakeConfig?.phrases?.length ? wakeConfig.phrases : DEFAULT_WAKE.phrases,
      response: wakeConfig?.response || '네. 말씀하세요.',
    }
  }, [wakeConfig])

  useEffect(() => {
    onWakeRef.current = onWake
  }, [onWake])

  useEffect(() => {
    onErrorRef.current = onError
  }, [onError])

  const clearRestartTimer = useCallback(() => {
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current)
      restartTimerRef.current = null
    }
  }, [])

  const canListenNow = useCallback(() => {
    const p = propsRef.current
    return p.enabled && !p.busy && !p.maintenance && !p.speaking && !p.commandActive
  }, [])

  const stopAmbient = useCallback(() => {
    activeRef.current = false
    clearRestartTimer()
    startingRef.current = false
    const recognition = recognitionRef.current
    recognitionRef.current = null
    detachRecognition(recognition)
    setIsAmbient(false)
  }, [clearRestartTimer])

  const scheduleRestart = useCallback(() => {
    if (!activeRef.current || !canListenNow()) {
      setIsAmbient(false)
      return
    }
    clearRestartTimer()
    restartTimerRef.current = setTimeout(() => {
      restartTimerRef.current = null
      if (activeRef.current && canListenNow()) {
        beginRecognitionRef.current?.()
      }
    }, RESTART_DELAY_MS)
  }, [canListenNow, clearRestartTimer])

  const beginRecognitionRef = useRef(null)

  const beginRecognition = useCallback(async () => {
    if (!supported || !activeRef.current || !canListenNow()) return
    if (recognitionRef.current || startingRef.current) return

    const now = Date.now()
    if (now - lastStartAtRef.current < MIN_RESTART_GAP_MS) {
      scheduleRestart()
      return
    }

    startingRef.current = true
    try {
      await primeAudioSession()
      const micOk = await ensureMicrophoneAccess()
      if (!micOk) {
        onErrorRef.current?.('마이크 권한이 필요합니다. Chrome 설정에서 마이크를 허용해 주세요.')
        activeRef.current = false
        return
      }
      if (!activeRef.current || !canListenNow()) return

      const SpeechRecognition = getSpeechRecognition()
      const recognition = new SpeechRecognition()
      recognition.lang = 'ko-KR'
      recognition.continuous = true
      recognition.interimResults = true
      recognition.maxAlternatives = 1

      recognition.onresult = (event) => {
        if (!activeRef.current) return
        let transcript = ''
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          transcript += event.results[i][0].transcript
        }
        const { phrases, response } = wakeConfigRef.current
        if (!containsWakeWord(transcript, phrases)) return

        activeRef.current = false
        clearRestartTimer()
        recognitionRef.current = null
        detachRecognition(recognition)
        setIsAmbient(false)
        onWakeRef.current?.(response)
      }

      recognition.onerror = (event) => {
        const code = event.error || ''
        if (code === 'aborted' || code === 'no-speech') return
        if (code === 'not-allowed' || code === 'service-not-allowed') {
          activeRef.current = false
          setIsAmbient(false)
          onErrorRef.current?.('마이크 권한이 필요합니다.')
          return
        }
        scheduleRestart()
      }

      recognition.onend = () => {
        if (recognitionRef.current === recognition) {
          recognitionRef.current = null
        }
        startingRef.current = false
        if (!activeRef.current) {
          setIsAmbient(false)
          return
        }
        scheduleRestart()
      }

      recognitionRef.current = recognition
      recognition.start()
      lastStartAtRef.current = Date.now()
      setIsAmbient(true)
    } catch (err) {
      recognitionRef.current = null
      setIsAmbient(false)
      if (activeRef.current) {
        scheduleRestart()
      }
      onErrorRef.current?.(err.message || '마이크를 시작할 수 없습니다')
    } finally {
      startingRef.current = false
    }
  }, [canListenNow, clearRestartTimer, scheduleRestart, supported])

  beginRecognitionRef.current = beginRecognition

  const wantAmbient = enabled && !busy && !maintenance && !speaking && !commandActive

  useEffect(() => {
    if (wantAmbient && supported) {
      activeRef.current = true
      beginRecognitionRef.current?.()
    } else {
      stopAmbient()
    }
    return () => {
      stopAmbient()
    }
  }, [wantAmbient, supported, stopAmbient])

  return {
    supported,
    isAmbient,
    stopAmbient,
    startAmbient: beginRecognition,
  }
}
