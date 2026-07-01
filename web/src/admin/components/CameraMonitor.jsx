import { useEffect, useRef, useState } from 'react'

export default function CameraMonitor({ className = '' }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function startCamera() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setStatus('error')
        setError('이 브라우저는 카메라를 지원하지 않습니다.')
        return
      }

      setStatus('loading')
      setError('')

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: 'user',
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
          audio: false,
        })
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }
        setStatus('live')
      } catch (err) {
        if (cancelled) return
        setStatus('error')
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          setError('카메라 권한이 거부되었습니다.')
        } else if (err.name === 'NotFoundError') {
          setError('연결된 카메라를 찾을 수 없습니다.')
        } else {
          setError(err.message || '카메라를 시작하지 못했습니다.')
        }
      }
    }

    startCamera()

    return () => {
      cancelled = true
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop())
        streamRef.current = null
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null
      }
    }
  }, [])

  return (
    <section className={`admin-camera-monitor ${className}`.trim()} aria-label="카메라 모니터링">
      <div className="admin-camera-monitor-header">
        <h2 className="admin-camera-monitor-title">모니터링</h2>
        <StatusDot status={status} />
      </div>
      <div className="admin-camera-monitor-frame">
        <video
          ref={videoRef}
          className="admin-camera-monitor-video"
          autoPlay
          playsInline
          muted
        />
        {status === 'loading' && (
          <div className="admin-camera-monitor-overlay">카메라 연결 중…</div>
        )}
        {status === 'error' && (
          <div className="admin-camera-monitor-overlay admin-camera-monitor-overlay--error">
            {error}
          </div>
        )}
      </div>
    </section>
  )
}

function StatusDot({ status }) {
  const label =
    status === 'live' ? 'LIVE' : status === 'loading' ? '연결 중' : '오류'
  const kind =
    status === 'live' ? 'on' : status === 'loading' ? 'warn' : 'danger'
  return (
    <span className={`admin-camera-status admin-camera-status--${kind}`}>
      {label}
    </span>
  )
}
