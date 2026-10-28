import { request, requestBlob } from '@/shared/api/http'
import type { ReportMeta } from '@/shared/types'

export const reportsApi = {
  generate(sessionId: string, regenerate = false): Promise<ReportMeta> {
    return request<ReportMeta>(`/sessions/${encodeURIComponent(sessionId)}/report/`, {
      method: 'POST',
      body: { regenerate },
    })
  },

  latest(sessionId: string): Promise<ReportMeta> {
    return request<ReportMeta>(`/sessions/${encodeURIComponent(sessionId)}/report/`)
  },

  forSession(sessionId: string): Promise<ReportMeta[]> {
    return request<ReportMeta[]>(
      `/sessions/${encodeURIComponent(sessionId)}/reports/`,
    )
  },

  all(sessionId?: string): Promise<ReportMeta[]> {
    const suffix = sessionId ? `?session=${encodeURIComponent(sessionId)}` : ''
    return request<ReportMeta[]>(`/reports/${suffix}`)
  },

  async download(report: ReportMeta): Promise<void> {
    const blob = await requestBlob(`/reports/${report.id}/download/`)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${report.report_id}-${report.patient_code}.pdf`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
  },
}
