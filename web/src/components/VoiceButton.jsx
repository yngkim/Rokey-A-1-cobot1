export function VoiceButton({
  supported,
  disabled,
  isListening,
  isProcessing,
  isAmbient = false,
  interimText,
  onPress,
  compact = false,
}) {
  const active = isListening || isProcessing

  return (
    <div className={`voice-panel ${compact ? 'voice-panel-compact' : ''}`}>
      {isAmbient && !active && (
        <p className="voice-ambient-badge" aria-live="polite">
          🎧 듣는 중 — 「돌봄아」라고 불러 주세요
        </p>
      )}
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
          명령을 말씀해 주세요
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
