import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import type { Account } from '../types'

export function useAccounts() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<Account[]>('/auth/accounts')
      setAccounts(data)
    } catch (err) {
      console.error('Failed to load accounts:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const addAccount = useCallback(async () => {
    try {
      const data = await apiFetch<{ auth_url: string }>('/auth/google')
      window.open(data.auth_url, '_blank')
    } catch (err) {
      console.error('Failed to initiate OAuth:', err)
    }
  }, [])

  const removeAccount = useCallback(async (id: number) => {
    await apiFetch(`/auth/accounts/${id}`, { method: 'DELETE' })
    setAccounts(prev => prev.filter(a => a.id !== id))
  }, [])

  return { accounts, loading, addAccount, removeAccount, reload: load }
}
