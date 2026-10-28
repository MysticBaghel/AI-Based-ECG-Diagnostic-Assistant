import { useResource, type Resource } from '@/shared/api/useResource'
import type { Session } from '@/shared/types'
import { sessionsApi, type SessionFilters } from '../api'

export function useSessions(
  params: SessionFilters = {},
  enabled = true,
): Resource<Session[]> {
  const key = `sessions:${params.patient ?? 'all'}:${params.status ?? 'all'}:${params.q ?? ''}`
  return useResource(key, () => sessionsApi.list(params), { enabled, pollMs: 15_000 })
}

export function useSession(sessionId: string | undefined): Resource<Session> {
  return useResource(`session:${sessionId ?? ''}`, () => sessionsApi.get(sessionId ?? ''), {
    enabled: Boolean(sessionId),
    pollMs: 30_000,
  })
}
