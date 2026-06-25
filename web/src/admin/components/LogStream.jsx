import { formatTs } from '../../api/adminClient'

export default function LogStream({ logs, paused, filter = 'all' }) {
  const filtered =
    filter === 'all' ? logs : logs.filter((line) => line.type === filter)

  return (
    <div className="admin-log-stream">
      {filtered.length === 0 && <div className="admin-log-line">로그 없음</div>}
      {filtered.map((line) => (
        <div key={line.id} className={`admin-log-line ${line.type}`}>
          {formatTs(line.ts)} {line.text}
        </div>
      ))}
      {!paused && filtered.length > 0 && <div ref={(el) => el?.scrollIntoView?.()} />}
    </div>
  )
}
