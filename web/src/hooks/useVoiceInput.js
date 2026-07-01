import { useCallback, useEffect, useRef, useState } from 'react'
import { sendVoiceCommand } from '../api/client'
import { ensureMicrophoneAccess, primeAudioSession } from '../speech/audioPrime'

function getSpeechRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

const ERROR_MESSAGES = {
  'not-allowed': '마이크 권한이 필요합니다. Chrome 설정에서 마이크를 허용해 주세요.',
  'service-not-allowed': '마이크를 사용할 수 없습니다. http://127.0.0.1:8080 으로 접속했는지 확인해 주세요.',
  'no-speech': '음성이 인식되지 않았습니다. 다시 말씀해 주세요.',
  'audio-capture': '마이크를 찾을 수 없습니다.',
  'network': '음성 인식 네트워크 오류입니다. 인터넷 연결을 확인해 주세요.',
  'aborted': '음성 인식이 중단되었습니다.',
}

function stripWakePrefix(text, wakePhrases = []) {
  let result = text.trim()
  for (const phrase of wakePhrases) {
    const re = new RegExp(`^${phrase.replace(/\s+/g, '\\s*')}\\s*`, 'i')
    result = result.replace(re, '').trim()
  }
  return result
}

export function useVoiceInput({
  enabled,
  busy,
  isSpeaking,
  wakePhrases = [],
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

  const startListening = useCallback(async () => {
    if (!supported || !enabled || busy || isSpeaking()) return false

    await primeAudioSession()
    const micOk = await ensureMicrophoneAccess()
    if (!micOk) {
      onError?.(ERROR_MESSAGES['not-allowed'])
      return false
    }

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
      const code = event.error || ''
      if (code === 'aborted') return
      onError?.(ERROR_MESSAGES[code] || `음성 인식 오류 (${code || 'unknown'})`)
    }

    recognition.onend = async () => {
      let text = transcriptRef.current.trim()
      setState('idle')
      setInterimText('')
      recognitionRef.current = null

      if (wakePhrases.length) {
        text = stripWakePrefix(text, wakePhrases)
      }

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
  }, [busy, enabled, isSpeaking, onError, onResult, supported, wakePhrases])

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
