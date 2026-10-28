import { request } from '@/shared/api/http'
import type { TokenPair, User } from '@/shared/types'

export const authApi = {
  login(username: string, password: string): Promise<TokenPair> {
    return request<TokenPair>('/auth/login/', {
      method: 'POST',
      body: { username, password },
      auth: false,
    })
  },

  me(): Promise<User> {
    return request<User>('/auth/me/')
  },
}
