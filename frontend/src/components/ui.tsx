import { useState, type ReactNode } from 'react'

import type { SessionState } from '../api/types'
import { Icon, type IconName } from './Icon'

export type Tone = 'ok' | 'warn' | 'bad' | 'neutral' | 'info'

export function Badge({
  tone = 'neutral',
  children,
  dot = true,
  pulse = false,
}: {
  tone?: Tone
  children: ReactNode
  dot?: boolean
  pulse?: boolean
}) {
  return (
    <span className={`badge badge--${tone}`}>
      {dot && <span className={`badge__dot${pulse ? ' badge__dot--pulse' : ''}`} />}
      {children}
    </span>
  )
}

const SESSION_TONE: Record<SessionState, Tone> = {
  active: 'ok',
  completed: 'neutral',
  aborted: 'bad',
}

export function SessionBadge({ status }: { status: SessionState }) {
  return (
    <Badge tone={SESSION_TONE[status]} pulse={status === 'active'}>
      {status}
    </Badge>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="spinner" role="status" aria-live="polite">
      <span className="spinner__ring" />
      <span>{label}</span>
    </div>
  )
}

export function ErrorBanner({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="banner banner--error" role="alert">
      <Icon name="alert" size={18} />
      <div className="banner__body">
        <strong>Something needs attention</strong>
        <span>{message}</span>
      </div>
      {onRetry && (
        <button type="button" className="button button--ghost button--sm" onClick={onRetry}>
          <Icon name="refresh" size={15} />
          Retry
        </button>
      )}
    </div>
  )
}

export function Notice({
  tone = 'info',
  icon = 'shield',
  children,
}: {
  tone?: Tone
  icon?: IconName
  children: ReactNode
}) {
  return (
    <div className={`banner banner--${tone}`}>
      <Icon name={icon} size={18} />
      <div className="banner__body">{children}</div>
    </div>
  )
}

export function EmptyState({
  icon = 'spark',
  title,
  description,
  action,
}: {
  icon?: IconName
  title: string
  description: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="empty">
      <div className="empty__icon">
        <Icon name={icon} size={26} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action && <div className="empty__action">{action}</div>}
    </div>
  )
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-header__description">{description}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  )
}

export function SectionCard({
  title,
  subtitle,
  actions,
  children,
  flush = false,
}: {
  title?: string
  subtitle?: string
  actions?: ReactNode
  children: ReactNode
  flush?: boolean
}) {
  return (
    <section className="panel">
      {(title || actions) && (
        <div className="panel__header">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {actions && <div className="panel__actions">{actions}</div>}
        </div>
      )}
      <div className={flush ? '' : 'panel__body'}>{children}</div>
    </section>
  )
}

export function StatCard({
  icon,
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  icon: IconName
  label: string
  value: ReactNode
  hint?: string
  tone?: Tone
}) {
  return (
    <div className={`stat stat--${tone}`}>
      <div className="stat__icon">
        <Icon name={icon} size={20} />
      </div>
      <div className="stat__body">
        <span className="stat__label">{label}</span>
        <strong className="stat__value">{value}</strong>
        {hint && <span className="stat__hint">{hint}</span>}
      </div>
    </div>
  )
}

export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      // Clipboard API needs a secure context; fall back to a hidden textarea.
      const area = document.createElement('textarea')
      area.value = value
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      document.body.removeChild(area)
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  return (
    <button type="button" className="button button--ghost button--sm" onClick={copy}>
      <Icon name={copied ? 'check' : 'copy'} size={15} />
      {copied ? 'Copied' : label}
    </button>
  )
}
