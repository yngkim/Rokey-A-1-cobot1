import { useCallback, useEffect, useRef, useState } from 'react'
import { sendVoiceCommand } from '../api/client'

function getSpeechRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

export function useVoiceInput({
  enabled,
  busy,
  isSpeaking,
  onResult,
  onError,
}) {
  const [state, setState] = useState('idle')
  const [interimText, setInterimText] = useState('')
  const recognitionRef = useRef(null)
  const transcriptRef = useRef('')

  const supported = typeof window !== 'undefined' && !!getSpeechRecognition()

  const stopListening = useCallback(() => {
    const recognition = recognitionRef.current
    if (recognition) {
      try {
        recognition.stop()
      } catch {
        // already stopped
      }
    }
    recognitionRef.current = null
  }, [])

  const startListening = useCallback(() => {
    if (!supported || !enabled || busy || isSpeaking()) return false

    const SpeechRecognition = getSpeechRecognition()
    const recognition = new SpeechRecognition()
    recognition.lang = 'ko-KR'
    recognition.continuous = false
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    transcriptRef.current = ''
    setInterimText('')
    setState('listening')

    recognition.onresult = (event) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        if (result.isFinal) {
          transcriptRef.current = result[0].transcript
        } else {
          interim += result[0].transcript
        }
      }
      setInterimText(interim)
    }

    recognition.onerror = (event) => {
      setState('idle')
      setInterimText('')
      onError?.(event.error || '음성 인식 오류')
    }

    recognition.onend = async () => {
      const text = transcriptRef.current.trim()
      setState('idle')
      setInterimText('')
      recognitionRef.current = null

      if (!text) {
        onError?.('음성이 인식되지 않았습니다')
        return
      }

      setState('processing')
      try {
        const result = await sendVoiceCommand(text)
        await onResult?.(result, text)
      } catch (err) {
        onError?.(err.message || '음성 명령 전송 실패')
      } finally {
        setState('idle')
      }
    }

    recognitionRef.current = recognition
    try {
      recognition.start()
      return true
    } catch (err) {
      setState('idle')
      onError?.(err.message || '마이크를 시작할 수 없습니다')
      return false
    }
  }, [busy, enabled, isSpeaking, onError, onResult, supported])

  useEffect(() => () => stopListening(), [stopListening])

  return {
    supported,
    state,
    interimText,
    isListening: state === 'listening',
    isProcessing: state === 'processing',
    startListening,
    stopListening,
  }
}
