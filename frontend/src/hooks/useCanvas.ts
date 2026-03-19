import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import type { CanvasConfig } from '../types'

export function useCanvas() {
  const [configs, setConfigs] = useState<CanvasConfig[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<CanvasConfig[]>('/canvas/configs')
      setConfigs(data)
    } catch (err) {
      console.error('Failed to load canvas configs:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const setup = useCallback(async (canvasUrl: string) => {
    try {
      const result = await apiFetch<{ status: string; config_id?: number }>(
        `/canvas/setup?canvas_url=${encodeURIComponent(canvasUrl)}`,
        { method: 'POST' }
      )
      if (result.status === 'ok') {
        await load()
      }
      return result
    } catch (err) {
      console.error('Canvas setup failed:', err)
      return { status: 'error' }
    }
  }, [load])

  const relogin = useCallback(async (configId: number) => {
    await apiFetch(`/canvas/relogin/${configId}`, { method: 'POST' })
    await load()
  }, [load])

  const remove = useCallback(async (configId: number) => {
    await apiFetch(`/canvas/configs/${configId}`, { method: 'DELETE' })
    setConfigs(prev => prev.filter(c => c.id !== configId))
  }, [])

  return { configs, loading, setup, relogin, remove, reload: load }
}
