import { pickKoreanVoice, prepareSpeechVoices, unlockMediaAudio } from './audioPrime'

const API_BASE = import.meta.env.VITE_API_BASE || ''

let speaking = false
let currentAudio = null
let currentObjectUrl = null

function cleanupPlayback() {
  if (currentAudio) {
    currentAudio.pause()
    currentAudio.src = ''
    currentAudio = null
  }
  if (currentObjectUrl) {
    URL.revokeObjectURL(currentObjectUrl)
    currentObjectUrl = null
  }
  speaking = false
}

async function fetchTtsBlob(text) {
  const res = await fetch(`${API_BASE}/api/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `TTS HTTP ${res.status}`)
  }
  return res.blob()
}

/** HTML Audio — Android STREAM_MUSIC(유튜브·영상과 동일 미디어 볼륨) */
async function speakViaMediaAudio(text) {
  await unlockMediaAudio()
  const blob = await fetchTtsBlob(text)
  const url = URL.createObjectURL(blob)
  currentObjectUrl = url

  return new Promise((resolve) => {
    const audio = new Audio(url)
    audio.preload = 'auto'
    audio.volume = 1
    audio.setAttribute('playsinline', '')
    currentAudio = audio
    speaking = true

    const finish = () => {
      cleanupPlayback()
      resolve()
    }

    audio.onended = finish
    audio.onerror = finish

    audio.play().catch(finish)
  })
}

/** Web Speech API — 기기 TTS(삼성: 알림/접근성 볼륨일 수 있음) 폴백 */
async function speakViaSpeechSynthesis(text) {
  if (!window.speechSynthesis) return

  await prepareSpeechVoices()
  const synth = window.speechSynthesis
  synth.cancel()
  synth.resume()

  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'ko-KR'
    utterance.volume = 1
    const voice = pickKoreanVoice()
    if (voice) utterance.voice = voice

    const finish = () => {
      speaking = false
      resolve()
    }

    utterance.onend = finish
    utterance.onerror = finish
    speaking = true
    synth.speak(utterance)
  })
}

export function isSpeaking() {
  return speaking
}

export function cancelSpeech() {
  cleanupPlayback()
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel()
  }
}

export async function speak(text) {
  if (!text?.trim()) return

  cancelSpeech()

  try {
    await speakViaMediaAudio(text)
  } catch {
    await speakViaSpeechSynthesis(text)
  }
}

if (typeof window !== 'undefined' && window.speechSynthesis) {
  window.speechSynthesis.onvoiceschanged = () => pickKoreanVoice()
}
