export function VoiceButton({
  supported,
  disabled,
  isListening,
  isProcessing,
  interimText,
  onPress,
}) {
  const active = isListening || isProcessing

  return (
    <div className="voice-panel">
      <button
        type="button"
        className={`voice-btn ${active ? 'voice-btn-active' : ''}`}
        onClick={onPress}
        disabled={disabled || !supported}
        aria-pressed={isListening}
        title={supported ? '음성 명령' : '이 브라우저는 음성 인식을 지원하지 않습니다'}
      >
        <span className="voice-btn-icon" aria-hidden="true">
          {active ? '🎙️' : '🎤'}
        </span>
        <span className="voice-btn-label">
          {isProcessing ? '처리 중…' : isListening ? '듣고 있어요…' : '음성 명령'}
        </span>
      </button>

      {isListening && (
        <p className="voice-hint">
          「약 준비해 줘」라고 말씀해 주세요
          {interimText ? (
            <span className="voice-interim"> — {interimText}</span>
          ) : null}
        </p>
      )}

      {!supported && (
        <p className="voice-hint voice-hint-warn">Chrome 또는 Edge에서 사용해 주세요.</p>
      )}
    </div>
  )
}

export default VoiceButton
