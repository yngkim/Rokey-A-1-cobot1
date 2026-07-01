function formatSavedAt(ts) {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function MedicationScheduleList({
  schedules,
  loading,
  disabled,
  editingId,
  onEdit,
  onDelete,
}) {
  if (loading) {
    return (
      <section className="med-schedule-list">
        <h2 className="med-schedule-list-title">저장된 약 시간</h2>
        <p className="med-schedule-list-empty">불러오는 중…</p>
      </section>
    )
  }

  return (
    <section className="med-schedule-list">
      <h2 className="med-schedule-list-title">저장된 약 시간</h2>
      {schedules.length === 0 ? (
        <p className="med-schedule-list-empty">저장된 약 시간이 없습니다.</p>
      ) : (
        <ul className="med-schedule-list-items">
          {schedules.map((item) => (
            <li
              key={item.id}
              className={[
                'med-schedule-list-item',
                editingId === item.id ? 'med-schedule-list-item-editing' : '',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              <div className="med-schedule-list-main">
                <span className="med-schedule-list-badge">{item.mode_label}</span>
                <span className="med-schedule-list-summary">{item.summary}</span>
                <span
                  className={[
                    'med-schedule-list-status',
                    item.enabled ? 'med-schedule-list-status-on' : 'med-schedule-list-status-off',
                  ].join(' ')}
                >
                  {item.enabled ? '자동 켜짐' : '꺼짐'}
                </span>
              </div>
              <p className="med-schedule-list-meta">
                저장: {formatSavedAt(item.updated_at || item.created_at)}
              </p>
              <div className="med-schedule-list-actions">
                <button
                  type="button"
                  className="med-schedule-list-btn med-schedule-list-btn-edit"
                  onClick={() => onEdit?.(item)}
                  disabled={disabled}
                >
                  수정
                </button>
                <button
                  type="button"
                  className="med-schedule-list-btn med-schedule-list-btn-delete"
                  onClick={() => onDelete?.(item)}
                  disabled={disabled}
                >
                  삭제
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
