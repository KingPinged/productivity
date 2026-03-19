const getToken = (): string => {
  return (window as any).__PLANNER_TOKEN__ || ''
}

const BASE = ''

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
      ...options?.headers,
    },
  })
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`)
  }
  return resp.json()
}
