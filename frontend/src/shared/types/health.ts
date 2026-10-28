export interface Health {
  status: string
  service: string
  analysis?: {
    dsp: string
    inference_available: boolean
    model_name: string | null
    model_version: string | null
    inference_reason: string
  }
}
