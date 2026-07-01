export default function DeviceLayoutToggle({ layout, onChange, disabled }) {
  return (
    <div className="layout-toggle" role="group" aria-label="화면 레이아웃">
      <button
        type="button"
        className={`layout-toggle-btn ${layout === 'phone' ? 'active' : ''}`}
        onClick={() => onChange('phone')}
        disabled={disabled}
        aria-pressed={layout === 'phone'}
      >
        핸드폰
      </button>
      <button
        type="button"
        className={`layout-toggle-btn ${layout === 'tablet' ? 'active' : ''}`}
        onClick={() => onChange('tablet')}
        disabled={disabled}
        aria-pressed={layout === 'tablet'}
      >
        태블릿
      </button>
    </div>
  )
}
