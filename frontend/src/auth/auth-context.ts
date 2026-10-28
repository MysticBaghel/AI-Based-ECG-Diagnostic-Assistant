import { createContext } from 'react'

import type { User } from '../api/types'

export type AuthStatus = 'loading' | 'anonymous' | 'authenticated'

export interface AuthValue {
  status: AuthStatus
  user: User | null
  login: (username: string, password: string) => Promise<User>
  logout: () => void
}

export const AuthContext = createContext<AuthValue | null>(null)
