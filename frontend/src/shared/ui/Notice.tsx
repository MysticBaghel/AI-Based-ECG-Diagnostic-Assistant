import type { ReactNode } from 'react'

import { Icon, type IconName } from '@/shared/icons/Icon'
import type { Tone } from './tone'

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
