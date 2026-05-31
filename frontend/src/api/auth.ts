import http from './http'

export interface AuthUser {
  id: number
  username: string
  disabled?: boolean
  created_at?: string
  updated_at?: string
}

interface ApiResponse {
  ok: boolean
  error?: string
  authenticated?: boolean
  bootstrap_required?: boolean
  user?: Record<string, unknown>
}

function normalizeUser(raw: unknown): AuthUser | null {
  const payload = (raw || {}) as Record<string, unknown>
  const username = String(payload.username || '').trim()
  if (!username) return null
  return {
    id: Math.max(0, Number(payload.id || 0)),
    username,
    disabled: Boolean(payload.disabled),
    created_at: String(payload.created_at || ''),
    updated_at: String(payload.updated_at || ''),
  }
}

export async function fetchAuthSession() {
  const { data } = await http.get<ApiResponse>('/api/auth/session')
  return {
    authenticated: Boolean(data.authenticated),
    bootstrapRequired: Boolean(data.bootstrap_required),
    user: normalizeUser(data.user),
  }
}

export async function bootstrapAuthUser(input: { username: string; password: string }) {
  const { data } = await http.post<ApiResponse>('/api/auth/bootstrap', input)
  return {
    authenticated: Boolean(data.authenticated),
    bootstrapRequired: Boolean(data.bootstrap_required),
    user: normalizeUser(data.user),
  }
}

export async function login(input: { username: string; password: string }) {
  const { data } = await http.post<ApiResponse>('/api/auth/login', input)
  return {
    authenticated: Boolean(data.authenticated),
    bootstrapRequired: Boolean(data.bootstrap_required),
    user: normalizeUser(data.user),
  }
}

export async function logout() {
  await http.post('/api/auth/logout')
}

export async function changePassword(input: { current_password: string; new_password: string }) {
  const { data } = await http.post<ApiResponse>('/api/auth/change-password', input)
  return {
    user: normalizeUser(data.user),
  }
}
