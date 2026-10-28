import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { healthApi } from '@/shared/api/health'
import { useResource } from '@/shared/api/useResource'
import { Icon } from '@/shared/icons/Icon'

export function Notifications() {
  const [open, setOpen] = useState(false)
  const hostRef = useRef<HTMLDivElement>(null)
  const health = useResource(
    'shell-health',
    async () => {
      const [django, fastapi] = await Promise.allSettled([
        healthApi.django(),
        healthApi.telemetry(),
      ])
      return {
        django: django.status === 'fulfilled',
        fastapi: fastapi.status === 'fulfilled',
        analysis: fastapi.status === 'fulfilled' ? fastapi.value.analysis : undefined,
      }
    },
    { pollMs: 30_000 },
  )

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (!hostRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const attention = !health.data?.fastapi || !health.data?.analysis?.inference_available

  return (
    <div className="topbar-bell" ref={hostRef}>
      <button
        type="button"
        className="icon-button"
        aria-label="Notifications"
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="bell" size={19} />
        {attention && <span className="topbar-bell__dot" />}
      </button>
      {open && (
        <div className="topbar-popover topbar-popover--bell">
          <strong>System status</strong>
          <div className="status-row">
            <span className={`status-dot ${health.data?.django ? 'status-dot--ok' : 'status-dot--bad'}`} />
            Django API
            <span>{health.data?.django ? 'up' : 'down'}</span>
          </div>
          <div className="status-row">
            <span className={`status-dot ${health.data?.fastapi ? 'status-dot--ok' : 'status-dot--bad'}`} />
            FastAPI telemetry
            <span>{health.data?.fastapi ? 'up' : 'down'}</span>
          </div>
          <div className="status-row">
            <span
              className={`status-dot ${health.data?.analysis?.inference_available ? 'status-dot--ok' : 'status-dot--warn'}`}
            />
            AI model
            <span>
              {health.data?.analysis?.inference_available ? 'ready' : 'not configured'}
            </span>
          </div>
          <Link to="/settings" className="topbar-popover__link" onClick={() => setOpen(false)}>
            Open settings
            <Icon name="chevron-right" size={14} />
          </Link>
        </div>
      )}
    </div>
  )
}
