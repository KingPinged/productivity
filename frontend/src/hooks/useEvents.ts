import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import type { CalendarEvent } from '../types'

export function useEvents(startAfter?: string, endBefore?: string) {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (startAfter) params.set('start_after', startAfter)
      if (endBefore) params.set('end_before', endBefore)
      const query = params.toString()
      const url = `/api/events${query ? `?${query}` : ''}`
      const data = await apiFetch<CalendarEvent[]>(url)
      setEvents(data)
    } catch (err) {
      console.error('Failed to load events:', err)
    } finally {
      setLoading(false)
    }
  }, [startAfter, endBefore])

  useEffect(() => { load() }, [load])

  return { events, loading, reload: load }
}
