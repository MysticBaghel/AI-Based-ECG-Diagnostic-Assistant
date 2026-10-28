export interface ReportMeta {
  id: string
  report_id: string
  session_id: string
  patient: number
  patient_name: string
  patient_code: string
  version: number
  file_size: number
  checksum: string
  generated_at: string
  generated_by: number | null
  download_url: string
  analysis_status: string
}
