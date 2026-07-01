/** 짧은 무음 WAV — 사용자 탭 직후 미디어(HTML Audio) 재생 잠금 해제용 */
const SILENT_WAV =
  'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQQAAAA='

let mediaAudioUnlocked = false
let micGranted = false
let unlockAudioEl = null

export function isMediaAudioUnlocked() {
  return mediaAudioUnlocked
}

/** HTML Audio(미디어 볼륨) 재생 채널 잠금 해제 — 버튼/음성 탭 직후 호출 */
export async function unlockMediaAudio() {
  if (mediaAudioUnlocked) return true
  try {
    const audio = unlockAudioEl || new Audio(SILENT_WAV)
    unlockAudioEl = audio
    audio.volume = 0.001
    audio.preload = 'auto'
    await audio.play()
    audio.pause()
    audio.currentTime = 0
    mediaAudioUnlocked = true
    return true
  } catch {
    return false
  }
}

export async function ensureMicrophoneAccess() {
  if (micGranted) return true
  if (!navigator.mediaDevices?.getUserMedia) return true

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    stream.getTracks().forEach((track) => track.stop())
    micGranted = true
    return true
  } catch {
    return false
  }
}

/** 사용자 탭 직후 — 미디어 TTS + 마이크 준비 */
export async function primeAudioSession() {
  const tts = await unlockMediaAudio()
  const mic = await ensureMicrophoneAccess()
  return { tts, mic }
}

/** Web Speech API 폴백용 (구형/서버 TTS 실패 시) */
export function pickKoreanVoice() {
  const voices = window.speechSynthesis?.getVoices?.() || []
  return (
    voices.find((v) => v.lang === 'ko-KR') ||
    voices.find((v) => v.lang.startsWith('ko')) ||
    voices[0] ||
    null
  )
}

export async function prepareSpeechVoices() {
  if (!window.speechSynthesis) return null
  const existing = window.speechSynthesis.getVoices()
  if (existing.length > 0) return pickKoreanVoice()

  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      window.speechSynthesis.onvoiceschanged = null
      resolve(pickKoreanVoice())
    }, 2000)

    window.speechSynthesis.onvoiceschanged = () => {
      clearTimeout(timer)
      window.speechSynthesis.onvoiceschanged = null
      resolve(pickKoreanVoice())
    }
  })
}
