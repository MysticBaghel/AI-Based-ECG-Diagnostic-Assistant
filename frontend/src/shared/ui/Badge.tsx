import type { ReactNode } from 'react'
import clsx from 'clsx'

import type { Tone } from './tone'

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
    <span className={clsx('badge', `badge--${tone}`)}>
      {dot && <span className={`badge__dot${pulse ? ' badge__dot--pulse' : ''}`} />}
      {children}
    </span>
  )
}
