import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, isAbortError } from '../api/client'

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
 * Load one API resource and keep it fresh.
 *
 * `key` is the identity of the request (a session id, the user id, "devices").
 * When it changes the resource is reloaded; when `pollMs` is set the loader runs
 * again in the background without clearing the data on screen, which is what
 * makes the heartbeat badges update without flickering.
 */
export function useResource<T>(
  key: string,
  load: () => Promise<T>,
  options: { pollMs?: number; enabled?: boolean } = {},
): Resource<T> {
  const { pollMs, enabled = true } = options
  const loadRef = useRef(load)
  const dataRef = useRef<T | null>(null)
  const [tick, setTick] = useState(0)

  const [state, setState] = useState<{
    data: T | null
    error: string | null
    loading: boolean
    refreshing: boolean
    updatedAt: number | null
  }>({ data: null, error: null, loading: true, refreshing: false, updatedAt: null })

  useEffect(() => {
    loadRef.current = load
  }, [load])

  const refresh = useCallback(() => setTick((value) => value + 1), [])

  useEffect(() => {
    if (!enabled) return

    let cancelled = false
    let timer: number | undefined

    async function run(background: boolean) {
      if (!background) {
        setState((previous) => ({
          ...previous,
          loading: previous.data === null,
          refreshing: previous.data !== null,
          error: null,
        }))
      } else {
        setState((previous) => ({ ...previous, refreshing: true }))
      }

      try {
        const data = await loadRef.current()
        if (cancelled) return
        dataRef.current = data
        setState({
          data,
          error: null,
          loading: false,
          refreshing: false,
          updatedAt: Date.now(),
        })
      } catch (error) {
        if (cancelled || isAbortError(error)) return
        setState((previous) => ({
          ...previous,
          loading: false,
          refreshing: false,
          error: messageFor(error),
        }))
      }
    }

    void run(dataRef.current !== null)
    if (pollMs && pollMs > 0) {
      timer = window.setInterval(() => {
        void run(true)
      }, pollMs)
    }

    return () => {
      cancelled = true
      if (timer !== undefined) window.clearInterval(timer)
    }
  }, [key, tick, pollMs, enabled])

  return {
    ...state,
    loading: enabled ? state.loading : false,
    refreshing: enabled ? state.refreshing : false,
    refresh,
  }
}
