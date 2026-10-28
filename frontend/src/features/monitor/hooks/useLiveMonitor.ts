import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '@/shared/api/http'
import { monitorApi, sensorSocketUrl } from '@/features/monitor/api'
import type { EcgChunk, EcgChunkSummary, Reading, SensorType, SocketFrame } from '@/shared/types'
import { buildEcgSeries, type EcgSeries } from '@/shared/lib/ecg'

export type ConnectionState = 'connecting' | 'live' | 'reconnecting' | 'closed' | 'error'

export interface LiveReadings {
  latest: Partial<Record<SensorType, Reading>>
  history: Record<SensorType, Reading[]>
  count: number
}

const EMPTY_READINGS: LiveReadings = {
  latest: {},
  history: { pulse: [], spo2: [], temperature: [], motion: [] },
  count: 0,
}

const EMPTY_SERIES: EcgSeries = {
  x: [],
  y: [],
  durationSeconds: 0,
  sampleCount: 0,
}

const WINDOW_SECONDS = 12
const MAX_READINGS_PER_SENSOR = 240
const MAX_CHUNKS = 18

function closeReason(code: number): string | null {
  if (code === 4401) {
    return 'The live socket rejected the access token. Sign in again.'
  }
  if (code === 4403) {
    return 'You are not allowed to watch this session.'
  }
  if (code === 4404) {
    return 'FastAPI does not know this session. Start FastAPI before the session, or re-register the session.'
  }
  return null
}

function messageFor(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Telemetry request failed.'
}

/**
 * One live session: a WebSocket for readings and chunk announcements, plus
 * REST for the chunk samples the socket deliberately does not carry.
 *
 * The socket can drop and reconnect; the REST seeding is what stops the chart
 * from starting empty every time a failed connection is retried.
 */
export function useLiveMonitor(sessionId: string | null) {
  const [readings, setReadings] = useState<LiveReadings>(EMPTY_READINGS)
  const [chunks, setChunks] = useState<EcgChunkSummary[]>([])
  const [series, setSeries] = useState<EcgSeries>(EMPTY_SERIES)
  const [connection, setConnection] = useState<ConnectionState>('connecting')
  const [socketError, setSocketError] = useState<string | null>(null)
  const [chunkError, setChunkError] = useState<string | null>(null)
  const [lastFrameAt, setLastFrameAt] = useState<number | null>(null)
  const [frames, setFrames] = useState(0)
  const [initialLoading, setInitialLoading] = useState(Boolean(sessionId))
  const [generation, setGeneration] = useState(0)

  const seenRef = useRef<Set<string>>(new Set())
  const chunkMapRef = useRef<Map<number, EcgChunk>>(new Map())
  const pendingRef = useRef<Set<number>>(new Set())

  const reconnect = useCallback(() => {
    setGeneration((value) => value + 1)
  }, [])

  useEffect(() => {
    if (!sessionId) return

    // The page mounts a fresh hook for every session id (the route passes a
    // `key`), so this effect only rewinds for a deliberate reconnect. Refs and
    // state therefore survive a socket drop while a new session starts clean.
    const activeSessionId = sessionId
    let disposed = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let pingTimer: number | undefined
    let attempt = 0

    function rebuild() {
      const ordered = [...chunkMapRef.current.values()]
      setSeries(buildEcgSeries(ordered, { maxSeconds: WINDOW_SECONDS }))
    }

    function addChunkSummary(summary: EcgChunkSummary) {
      setChunks((previous) => {
        if (previous.some((chunk) => chunk.chunk_index === summary.chunk_index)) {
          return previous
        }
        return [...previous, summary].sort((a, b) => a.chunk_index - b.chunk_index)
      })
    }

    async function fetchChunk(chunkIndex: number) {
      if (
        chunkMapRef.current.has(chunkIndex) ||
        pendingRef.current.has(chunkIndex)
      ) {
        return
      }
      pendingRef.current.add(chunkIndex)
      try {
        const chunk = await monitorApi.chunk(activeSessionId, chunkIndex)
        if (disposed) return
        chunkMapRef.current.set(chunk.chunk_index, chunk)

        // Bound the buffer: the chart only shows the last 12 seconds, but a
        // few extra chunks keep a re-render from trimming too eagerly.
        const ordered = [...chunkMapRef.current.keys()].sort((a, b) => a - b)
        while (ordered.length > MAX_CHUNKS) {
          const dropped = ordered.shift()
          if (dropped !== undefined) chunkMapRef.current.delete(dropped)
        }

        addChunkSummary({
          chunk_id: chunk.chunk_id,
          chunk_index: chunk.chunk_index,
          sample_rate_hz: chunk.sample_rate_hz,
          sample_count: chunk.sample_count,
          start_time: chunk.start_time,
          duration_seconds: chunk.duration_seconds,
        })
        setChunkError(null)
        rebuild()
      } catch (error) {
        if (!disposed) setChunkError(messageFor(error))
      } finally {
        pendingRef.current.delete(chunkIndex)
      }
    }

    function addReading(reading: Reading) {
      const key = `${reading.sensor_type}|${reading.recorded_at}`
      if (seenRef.current.has(key)) return
      seenRef.current.add(key)

      setReadings((previous) => {
        const history = {
          ...previous.history,
          [reading.sensor_type]: [
            ...(previous.history[reading.sensor_type] ?? []),
            reading,
          ].slice(-MAX_READINGS_PER_SENSOR),
        }
        return {
          latest: { ...previous.latest, [reading.sensor_type]: reading },
          history,
          count: previous.count + 1,
        }
      })
    }

    function handleFrame(frame: SocketFrame) {
      if (frame.event === 'snapshot') {
        for (const reading of frame.readings) addReading(reading)
        return
      }

      if (frame.event === 'reading') {
        addReading({
          reading_id: `${frame.sensor_type}|${frame.recorded_at}`,
          sensor_type: frame.sensor_type,
          value: frame.value,
          unit: frame.unit,
          recorded_at: frame.recorded_at,
        })
        return
      }

      if (frame.event === 'ecg_chunk') {
        addChunkSummary({
          chunk_id: `live-${frame.chunk_index}`,
          chunk_index: frame.chunk_index,
          sample_rate_hz: frame.sample_rate_hz,
          sample_count: frame.sample_count,
          start_time: frame.start_time,
          duration_seconds: frame.sample_count / frame.sample_rate_hz,
        })
        void fetchChunk(frame.chunk_index)
        return
      }

      if (frame.event === 'error') {
        setSocketError(frame.error.message)
      }
    }

    async function seedFromRest() {
      try {
        const index = await monitorApi.chunkIndex(activeSessionId)
        if (disposed) return
        setChunks(index.chunks)
        const recent = index.chunks.slice(-6)
        await Promise.all(recent.map((chunk) => fetchChunk(chunk.chunk_index)))
      } catch (error) {
        if (!disposed) setChunkError(messageFor(error))
      } finally {
        if (!disposed) setInitialLoading(false)
      }
    }

    function connect() {
      if (disposed) return
      setConnection(attempt === 0 ? 'connecting' : 'reconnecting')

      try {
        socket = new WebSocket(sensorSocketUrl(activeSessionId))
      } catch (error) {
        setSocketError(messageFor(error))
        setConnection('error')
        return
      }

      socket.onopen = () => {
        if (disposed) return
        attempt = 0
        setConnection('live')
        setSocketError(null)
        pingTimer = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) socket.send('ping')
        }, 20_000)
      }

      socket.onmessage = (event) => {
        if (disposed) return
        setLastFrameAt(Date.now())
        setFrames((value) => value + 1)
        try {
          handleFrame(JSON.parse(String(event.data)) as SocketFrame)
        } catch {
          // A malformed frame is the server's problem; keep the socket usable.
        }
      }

      socket.onclose = (event) => {
        if (pingTimer !== undefined) window.clearInterval(pingTimer)
        if (disposed) return

        const terminal = closeReason(event.code)
        if (terminal) {
          setConnection('error')
          setSocketError(terminal)
          return
        }

        attempt += 1
        setConnection('reconnecting')
        reconnectTimer = window.setTimeout(connect, Math.min(1000 * 2 ** attempt, 10_000))
      }
    }

    void seedFromRest()
    connect()

    return () => {
      disposed = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      if (pingTimer !== undefined) window.clearInterval(pingTimer)
      socket?.close(1000, 'viewer left')
    }
  }, [sessionId, generation])

  return {
    readings,
    chunks,
    series,
    connection,
    socketError,
    chunkError,
    lastFrameAt,
    frames,
    initialLoading,
    reconnect,
  }
}
