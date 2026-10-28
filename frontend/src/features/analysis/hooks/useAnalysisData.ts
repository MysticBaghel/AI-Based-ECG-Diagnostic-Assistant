import { useResource, type Resource } from '@/shared/api/useResource'
import { monitorApi } from '@/features/monitor/api'
import type { EcgChunk, EcgChunkList, ReportMeta } from '@/shared/types'
import { reportsApi } from '@/features/reports/api'

export function useReports(
  sessionId: string | undefined,
  enabled = true,
): Resource<ReportMeta[]> {
  return useResource(
    `reports:${sessionId ?? ''}`,
    () => reportsApi.forSession(sessionId ?? ''),
    { enabled: Boolean(sessionId) && enabled, pollMs: 30_000 },
  )
}

export function useChunkIndex(
  sessionId: string | undefined,
  enabled = true,
): Resource<EcgChunkList> {
  return useResource(
    `chunks:${sessionId ?? ''}`,
    () => monitorApi.chunkIndex(sessionId ?? ''),
    { enabled: Boolean(sessionId) && enabled, pollMs: 30_000 },
  )
}

export function useChunkWindow(
  sessionId: string | undefined,
  chunkIndexes: number[],
): Resource<EcgChunk[]> {
  const key = `chunk-window:${sessionId ?? ''}:${chunkIndexes.join(',')}`
  return useResource(
    key,
    () =>
      chunkIndexes.length === 0
        ? Promise.resolve([])
        : Promise.all(
            chunkIndexes.map((index) => monitorApi.chunk(sessionId ?? '', index)),
          ),
    { enabled: Boolean(sessionId) && chunkIndexes.length > 0 },
  )
}
