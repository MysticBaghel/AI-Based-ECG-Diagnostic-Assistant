import { request } from '@/shared/api/http'
import type { AnalysisResult } from '@/shared/types'

export interface AnalysisRecordResponse {
  status: string
  result: AnalysisResult
  error: string
}

export const analysisApi = {
  run(sessionId: string): Promise<AnalysisRecordResponse> {
    return request<AnalysisRecordResponse>(
      `/sessions/${encodeURIComponent(sessionId)}/analyze/`,
      { method: 'POST' },
    )
  },

  get(sessionId: string): Promise<AnalysisRecordResponse> {
    return request<AnalysisRecordResponse>(
      `/sessions/${encodeURIComponent(sessionId)}/analysis/`,
    )
  },
}
