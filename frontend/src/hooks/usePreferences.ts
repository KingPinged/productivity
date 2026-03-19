import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import type { Preferences } from '../types'

export function usePreferences() {
  const [prefs, setPrefs] = useState<Preferences>({})
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<Preferences>('/api/preferences')
      setPrefs(data)
    } catch (err) {
      console.error('Failed to load preferences:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const save = useCallback(async (updates: Preferences) => {
    await apiFetch('/api/preferences', {
      method: 'PATCH',
      body: JSON.stringify(updates),
    })
    setPrefs(prev => ({ ...prev, ...updates }))
  }, [])

  return { prefs, loading, save, reload: load }
}
