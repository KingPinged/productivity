import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'

interface Reminder {
  id: number
  remind_at: string
  reminder_type: string
  message: string
  urgent: boolean
  fired: boolean
}

export function useReminders() {
  const [reminders, setReminders] = useState<Reminder[]>([])

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<Reminder[]>('/api/reminders')
      setReminders(data)
    } catch (err) {
      console.error('Failed to load reminders:', err)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 30000) // Poll every 30s
    return () => clearInterval(interval)
  }, [load])

  const dismiss = useCallback(async (id: number) => {
    await apiFetch(`/api/reminders/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ action: 'dismiss' }),
    })
    setReminders(prev => prev.filter(r => r.id !== id))
  }, [])

  // Get reminders that are due now (remind_at <= current time)
  const dueReminders = reminders.filter(r => {
    const remindAt = new Date(r.remind_at)
    return remindAt <= new Date() && !r.fired
  })

  return { reminders: dueReminders, dismiss, reload: load }
}
