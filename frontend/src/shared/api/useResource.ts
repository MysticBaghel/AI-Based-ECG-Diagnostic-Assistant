import { useQuery } from '@tanstack/react-query'

import { ApiError } from './http'

export interface Resource<T> {
  data: T | null
  error: string | null
  loading: boolean
  refreshing: boolean
  updatedAt: number | null
  refresh: () => void
}

function messageFor(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}

/**
 * A thin TanStack Query adapter used by the feature hooks.
 *
 * Keeping this contract small means components stay independent of the query
 * library while still getting its cache, retries and background refresh.
 */
export function useResource<T>(
  key: string,
  load: () => Promise<T>,
  options: { pollMs?: number; enabled?: boolean } = {},
): Resource<T> {
  const { pollMs, enabled = true } = options
  const query = useQuery({
    queryKey: [key],
    queryFn: load,
    enabled,
    refetchInterval: enabled && pollMs ? pollMs : false,
    staleTime: pollMs ? Math.max(0, pollMs - 1_000) : 15_000,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
        return false
      }
      return failureCount < 1
    },
  })

  return {
    data: query.data ?? null,
    error: query.error ? messageFor(query.error) : null,
    loading: enabled ? query.isPending : false,
    refreshing: enabled ? query.isFetching && !query.isPending : false,
    updatedAt: query.dataUpdatedAt || null,
    refresh: () => {
      void query.refetch()
    },
  }
}
