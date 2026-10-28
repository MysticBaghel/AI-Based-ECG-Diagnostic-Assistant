import { useResource, type Resource } from '@/shared/api/useResource'
import type { AnalysisResult } from '@/shared/types'
import { monitorApi } from '../api'

export function useLiveAnalysis(
  sessionId: string | undefined,
  enabled: boolean,
): Resource<AnalysisResult> {
  return useResource(
    `live-analysis:${sessionId ?? ''}`,
    () => monitorApi.liveAnalysis(sessionId ?? ''),
    { enabled: Boolean(sessionId) && enabled, pollMs: 4_000 },
  )
}
