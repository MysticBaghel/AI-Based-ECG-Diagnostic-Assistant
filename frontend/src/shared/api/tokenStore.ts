import type { TokenPair } from '@/shared/types'

const ACCESS_KEY = 'ecg.access'
const REFRESH_KEY = 'ecg.refresh'
const PERSIST_KEY = 'ecg.persist'

export const AUTH_EXPIRED_EVENT = 'ecg:auth-expired'

export function isPersistent(): boolean {
  return localStorage.getItem(PERSIST_KEY) !== 'false'
}

export function setPersistent(value: boolean): void {
  localStorage.setItem(PERSIST_KEY, value ? 'true' : 'false')
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY) ?? sessionStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY) ?? sessionStorage.getItem(REFRESH_KEY)
}

export function storeTokens(tokens: TokenPair): void {
  const storage = isPersistent() ? localStorage : sessionStorage
  const other = isPersistent() ? sessionStorage : localStorage
  storage.setItem(ACCESS_KEY, tokens.access)
  storage.setItem(REFRESH_KEY, tokens.refresh)
  other.removeItem(ACCESS_KEY)
  other.removeItem(REFRESH_KEY)
}

export function clearTokens(): void {
  for (const storage of [localStorage, sessionStorage]) {
    storage.removeItem(ACCESS_KEY)
    storage.removeItem(REFRESH_KEY)
  }
}
