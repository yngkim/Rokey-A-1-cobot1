import TaskButton from './TaskButton'

const TABLET_TASK_ORDER = [
  'prepare_medication',
  'serve_meal',
  'return_tray',
  'clean_floor',
  'place_on_charger',
  'pick_from_charger',
  'go_home',
]

export default function TabletTaskGrid({
  tasks,
  canRun,
  disabledHint,
  phoneLocation,
  trayLocation,
  taskVoiceHints,
  activeUserId,
  onRun,
  onCareLog,
}) {
  const ordered = TABLET_TASK_ORDER.map((id) => tasks.find((t) => t.id === id)).filter(Boolean)
  const extras = tasks.filter((t) => !TABLET_TASK_ORDER.includes(t.id))
  const allTasks = [...ordered, ...extras]

  const taskHint = (taskId) => {
    if (taskId === 'pick_from_charger' && phoneLocation === 'with_user') {
      return '핸드폰은 이미 가져가셨어요'
    }
    if (taskId === 'place_on_charger' && phoneLocation === 'on_charger') {
      return '핸드폰은 이미 거치대에 있어요'
    }
    if (
      (taskId === 'serve_meal' || taskId === 'return_tray') &&
      trayLocation !== 'on_station'
    ) {
      return '트레이가 원위치에 없습니다'
    }
    return ''
  }

  return (
    <div className="tablet-task-grid">
      {allTasks.map((task) => {
        const hint = taskHint(task.id)
        return (
          <TaskButton
            key={task.id}
            task={task}
            layout="tablet"
            disabled={!canRun || !!hint}
            hint={hint || disabledHint}
            voiceHints={taskVoiceHints}
            onRun={onRun}
          />
        )
      })}

      <button
        type="button"
        className="task-btn task-btn-tablet"
        disabled={!canRun || !activeUserId}
        onClick={() => onCareLog('medication_taken', '복용 완료')}
        title={disabledHint || '복용 완료 기록'}
      >
        <span className="task-icon">✅</span>
        <span className="task-label">복용 완료</span>
      </button>
    </div>
  )
}
