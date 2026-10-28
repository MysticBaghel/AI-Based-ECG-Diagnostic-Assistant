import type { ReactNode } from 'react'

import { Icon, type IconName } from '@/shared/icons/Icon'

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
