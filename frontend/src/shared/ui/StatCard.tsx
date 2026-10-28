import type { ReactNode } from 'react'

import { Icon, type IconName } from '@/shared/icons/Icon'
import type { Tone } from './tone'

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
