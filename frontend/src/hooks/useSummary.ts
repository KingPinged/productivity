import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'

interface SummaryData {
  summary: string | null
  email_alerts: { subject: string; from: string; reason: string; urgent: boolean }[]
  tasks_today: string[]
  tasks_later: string[]
}

export function useSummary(date: string) {
  const [data, setData] = useState<SummaryData>({
    summary: null,
    email_alerts: [],
    tasks_today: [],
    tasks_later: [],
  })

  const load = useCallback(async () => {
    try {
      const result = await apiFetch<SummaryData>(`/api/summary/${date}`)
      setData(result)
    } catch (err) {
      console.error('Failed to load summary:', err)
    }
  }, [date])

  useEffect(() => { load() }, [load])

  return { ...data, reload: load }
}
