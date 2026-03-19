import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import type { DaySchedule } from '../types'

export function useSchedule(date: string) {
  const [schedule, setSchedule] = useState<DaySchedule | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<DaySchedule>(`/api/schedule/${date}`)
      setSchedule(data)
    } catch (err) {
      console.error('Failed to load schedule:', err)
    } finally {
      setLoading(false)
    }
  }, [date])

  useEffect(() => { load() }, [load])

  const updateBlock = useCallback(async (blockId: number, updates: Record<string, string>) => {
    await apiFetch(`/api/schedule/${blockId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    })
    await load()
  }, [load])

  const triggerReplan = useCallback(async () => {
    await apiFetch('/api/schedule/replan', {
      method: 'POST',
      body: JSON.stringify({ date }),
    })
    await load()
  }, [date, load])

  return { schedule, loading, updateBlock, triggerReplan, reload: load }
}
