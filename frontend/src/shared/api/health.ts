import { request } from './http'
import type { Health } from '@/shared/types'

export const healthApi = {
  django(): Promise<Health> {
    return request<Health>('/health/', { auth: false })
  },

  telemetry(): Promise<Health> {
    return request<Health>('/health', { auth: false, base: 'telemetry' })
  },
}
