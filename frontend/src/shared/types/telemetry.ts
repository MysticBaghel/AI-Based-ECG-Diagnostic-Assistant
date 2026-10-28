export type SensorType = 'temperature' | 'spo2' | 'pulse' | 'motion'

export interface Reading {
  reading_id: string
  sensor_type: SensorType
  value: number
  unit: string
  recorded_at: string
}

export interface ReadingsResponse {
  session_id: string
  count: number
  readings: Reading[]
}

export interface DeviceStatus {
  device_id: string
  owner_id: number | null
  last_seen: string | null
  seconds_since_seen: number | null
  online: boolean
  revoked: boolean
}

export interface StatusResponse {
  threshold_seconds: number
  devices: DeviceStatus[]
}

export interface EcgChunkSummary {
  chunk_id: string
  chunk_index: number
  sample_rate_hz: number
  sample_count: number
  start_time: string
  duration_seconds: number
}

export interface EcgChunkList {
  session_id: string
  count: number
  chunks: EcgChunkSummary[]
}

export interface EcgChunk extends EcgChunkSummary {
  session_id: string
  device_id: string
  samples: number[]
}

export type SocketFrame =
  | { event: 'snapshot'; session_id: string; readings: Reading[] }
  | {
      event: 'reading'
      session_id: string
      sensor_type: SensorType
      value: number
      unit: string
      recorded_at: string
    }
  | {
      event: 'ecg_chunk'
      session_id: string
      chunk_index: number
      sample_count: number
      sample_rate_hz: number
      start_time: string
    }
  | { event: 'error'; error: { code: string; message: string } }
  | { event: 'pong' }
