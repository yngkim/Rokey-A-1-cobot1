import { useState } from 'react'
import { getTaskVoiceHint } from '../api/client'

export default function TaskButton({
  task,
  disabled,
  hint,
  voicePhrase,
  voiceHints,
  layout = 'phone',
  onRun,
}) {
  const [loading, setLoading] = useState(false)
  const phrase = voicePhrase ?? getTaskVoiceHint(task.id, voiceHints)

  const handleClick = async () => {
    if (disabled || loading) return
    setLoading(true)
    try {
      await onRun(task.id)
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      type="button"
      className={[
        'task-btn',
        task.id === 'go_home' ? 'task-btn-control' : '',
        layout === 'tablet' ? 'task-btn-tablet' : '',
        loading ? 'loading' : '',
        disabled ? 'disabled' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      onClick={handleClick}
      disabled={disabled || loading}
      title={hint}
    >
      <span className="task-icon">{task.icon}</span>
      <span className="task-label">{task.label}</span>
      {phrase && (
        <span className={`task-voice-hint ${layout === 'tablet' ? 'task-voice-hint-tablet' : ''}`}>
          「{phrase}」
        </span>
      )}
      {loading && <span className="task-spinner" />}
    </button>
  )
}
