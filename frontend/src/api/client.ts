const getToken = (): string => {
  return localStorage.getItem('planner_token') || ''
}

export function setToken(token: string) {
  localStorage.setItem('planner_token', token)
}

export function clearToken() {
  localStorage.removeItem('planner_token')
}

export function hasToken(): boolean {
  return !!localStorage.getItem('planner_token')
}

const BASE = ''

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...options?.headers as Record<string, string>,
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const resp = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  })

  if (resp.status === 401) {
    clearToken()
    window.location.reload()
    throw new Error('Unauthorized')
  }

  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`)
  }
  return resp.json()
}
