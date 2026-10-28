import type { SessionState } from '@/shared/types'
import { Badge } from './Badge'
import type { Tone } from './tone'

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
