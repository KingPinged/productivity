import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'

interface UserContext {
  id: number
  message: string
  created_at: string
}

export function useUserContext() {
  const [messages, setMessages] = useState<UserContext[]>([])

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<UserContext[]>('/api/context')
      setMessages(data)
    } catch (err) {
      console.error('Failed to load context:', err)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const addMessage = useCallback(async (message: string) => {
    await apiFetch('/api/context', {
      method: 'POST',
      body: JSON.stringify({ message }),
    })
    await load()
  }, [load])

  const clearAll = useCallback(async () => {
    await apiFetch('/api/context', { method: 'DELETE' })
    setMessages([])
  }, [])

  return { messages, addMessage, clearAll, reload: load }
}
