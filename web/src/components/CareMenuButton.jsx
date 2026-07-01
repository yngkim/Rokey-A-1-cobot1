import { Link } from 'react-router-dom'

export default function CareMenuButton({ to, icon, label, hint, disabled }) {
  return (
    <Link
      to={to}
      className={`task-btn task-btn-menu ${disabled ? 'disabled' : ''}`}
      aria-disabled={disabled}
      onClick={(e) => {
        if (disabled) e.preventDefault()
      }}
    >
      <span className="task-icon">{icon}</span>
      <span className="task-label">{label}</span>
      {hint && <span className="task-voice-hint">{hint}</span>}
    </Link>
  )
}
