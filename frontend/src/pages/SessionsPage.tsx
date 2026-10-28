import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import type { SessionState } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { SessionTable } from '../components/SessionList'
import {
  EmptyState,
  ErrorBanner,
  PageHeader,
  Spinner,
  StatCard,
} from '../components/ui'
import { useSessions } from '../hooks/useData'
import { elapsedSeconds, formatDuration } from '../lib/format'

type Filter = 'all' | SessionState

export function SessionsPage() {
  const { user } = useAuth()
  const sessions = useSessions()
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')

  const patientFilter = params.get('patient')
  const list = sessions.data ?? []

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return (sessions.data ?? []).filter((session) => {
      if (filter !== 'all' && session.status !== filter) return false
      if (patientFilter && String(session.patient) !== patientFilter) return false
      if (!needle) return true
      return [session.patient_name, session.device_name, session.id]
        .join(' ')
        .toLowerCase()
        .includes(needle)
    })
  }, [sessions.data, filter, patientFilter, query])

  const active = list.filter((session) => session.status === 'active')
  const totalTime = list.reduce(
    (sum, session) => sum + elapsedSeconds(session.start_time, session.end_time),
    0,
  )
  const canManage = user?.role === 'doctor' || user?.role === 'admin'

  return (
    <>
      <PageHeader
        eyebrow="History"
        title="Sessions"
        description="Every monitoring session you may see. Active sessions open live; completed sessions open their stored waveform."
        actions={
          canManage && (
            <Link to="/patients" className="button button--primary">
              <Icon name="plus" size={16} />
              Start a session
            </Link>
          )
        }
      />

      {sessions.error && (
        <ErrorBanner message={sessions.error} onRetry={sessions.refresh} />
      )}

      <div className="stats stats--three">
        <StatCard
          icon="pulse"
          label="Active"
          value={active.length}
          hint="streaming now"
          tone={active.length > 0 ? 'ok' : 'neutral'}
        />
        <StatCard icon="sessions" label="Total sessions" value={list.length} hint="in view" />
        <StatCard
          icon="clock"
          label="Recorded time"
          value={formatDuration(totalTime)}
          hint="sum of completed and active"
        />
      </div>

      <div className="toolbar toolbar--wrap">
        <label className="search">
          <Icon name="search" size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search patient, device or session id…"
            aria-label="Search sessions"
          />
        </label>

        <div className="segmented" role="group" aria-label="Filter by status">
          {(['all', 'active', 'completed', 'aborted'] as Filter[]).map((value) => (
            <button
              type="button"
              key={value}
              className={`segmented__item${filter === value ? ' segmented__item--active' : ''}`}
              onClick={() => setFilter(value)}
            >
              {value}
            </button>
          ))}
        </div>

        {patientFilter && (
          <button
            type="button"
            className="chip"
            onClick={() => {
              const next = new URLSearchParams(params)
              next.delete('patient')
              setParams(next, { replace: true })
            }}
          >
            Patient #{patientFilter}
            <Icon name="close" size={13} />
          </button>
        )}

        <button
          type="button"
          className="button button--ghost button--sm"
          onClick={sessions.refresh}
          disabled={sessions.refreshing}
        >
          <Icon name="refresh" size={14} />
          {sessions.refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {sessions.loading ? (
        <Spinner label="Loading sessions…" />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon="sessions"
          title={list.length === 0 ? 'No sessions yet' : 'No session matches'}
          description={
            list.length === 0
              ? canManage
                ? 'Start a session for a patient, then run the simulator to fill it with data.'
                : 'Your care team has not started a session for you yet.'
              : 'Clear the search or choose a different status.'
          }
          action={
            list.length === 0 && canManage ? (
              <Link to="/patients" className="button button--primary">
                Choose a patient
              </Link>
            ) : undefined
          }
        />
      ) : (
        <SessionTable sessions={filtered} />
      )}

      <p className="muted small">
        Showing {filtered.length} of {list.length} sessions. Times are shown in your local
        timezone; the API stores UTC.
      </p>
    </>
  )
}
