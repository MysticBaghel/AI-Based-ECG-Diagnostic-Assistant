import type { SensorType } from '../api/types'

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return dateTimeFormatter.format(date)
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return timeFormatter.format(date)
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return dateFormatter.format(date)
}

/** "12s ago", "4m ago", "2h ago" - used for heartbeats and reading ages. */
export function formatRelative(value: string | null | undefined): string {
  if (!value) return 'never'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'never'
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000))
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${secs}s`
  return `${secs}s`
}

export function elapsedSeconds(start: string, end: string | null): number {
  const from = new Date(start).getTime()
  const to = end ? new Date(end).getTime() : Date.now()
  if (Number.isNaN(from) || Number.isNaN(to)) return 0
  return Math.max(0, (to - from) / 1000)
}

export function formatNumber(value: number, digits = 1): string {
  if (!Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

export function initials(name: string): string {
  return name
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

export interface SensorMeta {
  label: string
  shortLabel: string
  unit: string
  digits: number
  accent: string
  hint: string
}

export const SENSOR_META: Record<SensorType, SensorMeta> = {
  pulse: {
    label: 'Heart rate',
    shortLabel: 'Pulse',
    unit: 'bpm',
    digits: 0,
    accent: '#ff6b7a',
    hint: 'pulse sensor',
  },
  spo2: {
    label: 'Blood oxygen',
    shortLabel: 'SpO₂',
    unit: '%',
    digits: 1,
    accent: '#4fc3f7',
    hint: 'SpO₂ sensor',
  },
  temperature: {
    label: 'Temperature',
    shortLabel: 'Temp',
    unit: '°C',
    digits: 1,
    accent: '#ffb74d',
    hint: 'temperature sensor',
  },
  motion: {
    label: 'Motion',
    shortLabel: 'Motion',
    unit: 'a.u.',
    digits: 2,
    accent: '#b388ff',
    hint: 'motion sensor',
  },
}

export const SENSOR_ORDER: SensorType[] = ['pulse', 'spo2', 'temperature', 'motion']
