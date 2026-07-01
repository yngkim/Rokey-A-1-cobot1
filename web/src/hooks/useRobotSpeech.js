import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchVoiceCatalog } from '../api/client'
import { primeAudioSession } from '../speech/audioPrime'
import { cancelSpeech, isSpeaking as checkSpeaking, speak } from '../speech/ttsEngine'

const DEFAULT_SPEECH = {
  prepare_medication: {
    ack: '네, 약 준비해 드리겠습니다.',
    complete: '약 준비가 끝났어요.',
  },
  stop: {
    ack: '네, 멈추겠습니다.',
  },
  pick_phone: {
    ack: '네, 핸드폰 가져다 드릴게요.',
    arrival: '핸드폰 가져다 왔어요. 받아 주세요.',
    complete: '핸드폰 가져왔어요.',
  },
  place_phone: {
    ack: '네, 핸드폰 거치대에 갖다 놓을게요.',
    arrival: '핸드폰 올려 주세요. 기다리고 있을게요.',
    complete: '핸드폰을 거치대에 놓았어요.',
  },
  clean_floor: {
    ack: '네, 청소해 드릴게요.',
    complete: '청소가 끝났어요.',
  },
  serve_meal: {
    ack: '네, 식사 가져다 드릴게요.',
    arrival: '식사 가져다 왔어요. 받아 주세요.',
    complete: '식사 가져다 드렸어요.',
  },
  return_tray: {
    ack: '네, 식사 가져갈게요.',
    arrival: '트레이 회수하러 왔어요.',
    complete: '식사 가져갔어요.',
  },
  global: {
    not_understood: '잘 못 들었어요. 다시 말씀해 주세요.',
    busy: '지금 다른 일을 하고 있어요. 잠시만 기다려 주세요.',
    error: '작업 중 문제가 생겼어요.',
    phone_with_user: '핸드폰은 이미 가져가셨어요.',
    phone_on_charger: '핸드폰은 이미 거치대에 있어요.',
  },
}

export function useRobotSpeech() {
  const [speechCatalog, setSpeechCatalog] = useState(DEFAULT_SPEECH)
  const [speaking, setSpeaking] = useState(false)
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
    await primeAudioSession()
    setSpeaking(true)
    try {
      await speak(text)
    } finally {
      setSpeaking(false)
    }
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
    speaking,
    isSpeaking: checkSpeaking,
    cancelSpeech,
    speakAck,
    speakComplete,
    speakGlobal,
    speakFromResponse,
    speakText,
  }
}
