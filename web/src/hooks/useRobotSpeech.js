import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchVoiceCatalog } from '../api/client'
import { cancelSpeech, isSpeaking, speak } from '../speech/ttsEngine'

const DEFAULT_SPEECH = {
  prepare_medication: {
    ack: '네, 약 준비해 드리겠습니다.',
    complete: '약 준비가 끝났어요.',
  },
  stop: {
    ack: '네, 멈추겠습니다.',
  },
  global: {
    not_understood: '잘 못 들었어요. 다시 말씀해 주세요.',
    busy: '지금 다른 일을 하고 있어요. 잠시만 기다려 주세요.',
    error: '작업 중 문제가 생겼어요.',
  },
}

export function useRobotSpeech() {
  const [speechCatalog, setSpeechCatalog] = useState(DEFAULT_SPEECH)
  const catalogRef = useRef(DEFAULT_SPEECH)

  useEffect(() => {
    fetchVoiceCatalog()
      .then((data) => {
        if (data?.speech) {
          catalogRef.current = data.speech
          setSpeechCatalog(data.speech)
        }
      })
      .catch(() => {})
  }, [])

  const getText = useCallback((commandId, phase) => {
    const catalog = catalogRef.current
    if (phase === 'not_understood' || phase === 'busy' || phase === 'error') {
      return catalog.global?.[phase] || DEFAULT_SPEECH.global[phase] || ''
    }
    return catalog[commandId]?.[phase] || DEFAULT_SPEECH[commandId]?.[phase] || ''
  }, [])

  const speakText = useCallback(async (text) => {
    if (!text) return
    await speak(text)
  }, [])

  const speakAck = useCallback(
    async (commandId) => {
      await speakText(getText(commandId, 'ack'))
    },
    [getText, speakText],
  )

  const speakComplete = useCallback(
    async (commandId) => {
      await speakText(getText(commandId, 'complete'))
    },
    [getText, speakText],
  )

  const speakGlobal = useCallback(
    async (phase) => {
      await speakText(getText('global', phase))
    },
    [getText, speakText],
  )

  const speakFromResponse = useCallback(
    async (speech) => {
      if (speech?.text) {
        await speakText(speech.text)
      }
    },
    [speakText],
  )

  return {
    speechCatalog,
    isSpeaking,
    cancelSpeech,
    speakAck,
    speakComplete,
    speakGlobal,
    speakFromResponse,
    speakText,
  }
}
