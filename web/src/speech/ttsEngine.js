let speaking = false

function pickKoreanVoice() {
  const voices = window.speechSynthesis?.getVoices?.() || []
  return (
    voices.find((v) => v.lang === 'ko-KR') ||
    voices.find((v) => v.lang.startsWith('ko')) ||
    voices[0] ||
    null
  )
}

export function isSpeaking() {
  return speaking
}

export function cancelSpeech() {
  if (!window.speechSynthesis) return
  window.speechSynthesis.cancel()
  speaking = false
}

export function speak(text) {
  if (!text || !window.speechSynthesis) {
    return Promise.resolve()
  }

  cancelSpeech()

  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'ko-KR'
    const voice = pickKoreanVoice()
    if (voice) utterance.voice = voice

    utterance.onend = () => {
      speaking = false
      resolve()
    }
    utterance.onerror = () => {
      speaking = false
      resolve()
    }

    speaking = true
    window.speechSynthesis.speak(utterance)
  })
}

if (typeof window !== 'undefined' && window.speechSynthesis) {
  window.speechSynthesis.onvoiceschanged = () => pickKoreanVoice()
}
