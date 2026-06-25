export default function StatusBadge({ kind = 'info', children }) {
  return <span className={`admin-badge ${kind}`}>{children}</span>
}
