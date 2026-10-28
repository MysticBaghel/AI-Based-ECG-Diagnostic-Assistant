import type { ReactNode } from 'react'

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
