export type Role = 'operator' | 'admin'

export interface User {
  id: number
  username: string
  role: Role
  is_staff: boolean
}

export interface TokenPair {
  access: string
  refresh: string
}
