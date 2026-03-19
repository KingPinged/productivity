import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import type { Task } from '../types'

export function useTasks(source?: string, status?: string) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (source) params.set('source', source)
      if (status) params.set('status', status)
      const query = params.toString()
      const url = `/api/tasks${query ? `?${query}` : ''}`
      const data = await apiFetch<Task[]>(url)
      setTasks(data)
    } catch (err) {
      console.error('Failed to load tasks:', err)
    } finally {
      setLoading(false)
    }
  }, [source, status])

  useEffect(() => { load() }, [load])

  const addTask = useCallback(async (task: {
    title: string
    deadline?: string
    course?: string
    estimated_minutes?: number
    priority?: number
  }) => {
    const result = await apiFetch<{ task_id: number }>('/api/tasks', {
      method: 'POST',
      body: JSON.stringify(task),
    })
    await load()
    return result.task_id
  }, [load])

  const updateStatus = useCallback(async (taskId: number, newStatus: string) => {
    await apiFetch(`/api/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: newStatus }),
    })
    setTasks(prev => prev.map(t =>
      t.id === taskId ? { ...t, status: newStatus as Task['status'] } : t
    ))
  }, [])

  const deleteTask = useCallback(async (taskId: number) => {
    await apiFetch(`/api/tasks/${taskId}`, { method: 'DELETE' })
    setTasks(prev => prev.filter(t => t.id !== taskId))
  }, [])

  return { tasks, loading, addTask, updateStatus, deleteTask, reload: load }
}
