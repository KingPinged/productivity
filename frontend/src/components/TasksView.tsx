import { useState, useMemo, useCallback } from 'react'
import { useTasks } from '../hooks/useTasks'
import { useSchedule } from '../hooks/useSchedule'
import TaskCard from './TaskCard'
import QuickAddTask from './QuickAddTask'
import type { Task } from '../types'

function categorizeTask(task: Task): 'now' | 'later' | 'future' {
  if (!task.deadline) return 'future'
  const deadline = new Date(task.deadline)
  const now = new Date()
  const diffDays = Math.ceil((deadline.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  if (diffDays <= 1) return 'now'
  if (diffDays <= 7) return 'later'
  return 'future'
}

type Category = 'now' | 'later' | 'future'

const CATEGORIES: { key: Category; label: string; color: string }[] = [
  { key: 'now', label: 'Now', color: 'text-urgent' },
  { key: 'later', label: 'Later', color: 'text-amber-500' },
  { key: 'future', label: 'Future', color: 'text-accent' },
]

export default function TasksView() {
  const { tasks, loading, addTask, updateStatus, deleteTask } = useTasks(undefined, 'pending')
  const today = new Date().toISOString().split('T')[0]
  const { triggerReplan } = useSchedule(today)
  const [activeTab, setActiveTab] = useState<Category>('now')

  const handleToggleStatus = useCallback(async (taskId: number, newStatus: string) => {
    await updateStatus(taskId, newStatus)
    if (newStatus === 'done') {
      await triggerReplan()
    }
  }, [updateStatus, triggerReplan])

  const columns = useMemo(() => {
    const now: Task[] = []
    const later: Task[] = []
    const future: Task[] = []
    for (const task of tasks) {
      const cat = categorizeTask(task)
      if (cat === 'now') now.push(task)
      else if (cat === 'later') later.push(task)
      else future.push(task)
    }
    return { now, later, future }
  }, [tasks])

  if (loading) return <div className="text-muted">Loading tasks...</div>

  return (
    <div className="h-full flex flex-col">
      <QuickAddTask onAdd={addTask} />

      {/* Mobile: tab buttons */}
      <div className="flex md:hidden gap-2 mb-3">
        {CATEGORIES.map(({ key, label, color }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex-1 py-2 rounded-xl text-sm font-semibold transition-all ${
              activeTab === key
                ? `${color} bg-surface border border-border shadow-soft`
                : 'text-muted bg-cream'
            }`}
          >
            {label} ({columns[key].length})
          </button>
        ))}
      </div>

      {/* Mobile: show only active tab */}
      <div className="md:hidden flex-1 overflow-y-auto space-y-2 pb-4">
        {columns[activeTab].length === 0 ? (
          <p className="text-xs text-muted text-center mt-8">No tasks</p>
        ) : (
          columns[activeTab].map(task => (
            <TaskCard
              key={task.id}
              task={task}
              onToggleStatus={handleToggleStatus}
              onDelete={deleteTask}
            />
          ))
        )}
      </div>

      {/* Desktop: 3-column grid */}
      <div className="hidden md:grid flex-1 grid-cols-3 gap-4 min-h-0">
        <TaskColumn title="Now" subtitle="Due today/tomorrow" tasks={columns.now} accentColor="text-urgent" onToggleStatus={handleToggleStatus} onDelete={deleteTask} />
        <TaskColumn title="Later" subtitle="This week" tasks={columns.later} accentColor="text-amber-500" onToggleStatus={handleToggleStatus} onDelete={deleteTask} />
        <TaskColumn title="Future" subtitle="Beyond this week" tasks={columns.future} accentColor="text-accent" onToggleStatus={handleToggleStatus} onDelete={deleteTask} />
      </div>
    </div>
  )
}

function TaskColumn({
  title, subtitle, tasks, accentColor, onToggleStatus, onDelete,
}: {
  title: string
  subtitle: string
  tasks: Task[]
  accentColor: string
  onToggleStatus: (id: number, status: string) => void
  onDelete: (id: number) => void
}) {
  return (
    <div className="flex flex-col min-h-0">
      <div className="mb-3">
        <h3 className={`font-display font-semibold text-sm uppercase tracking-wider ${accentColor}`}>{title}</h3>
        <p className="text-xs text-muted">{subtitle}</p>
        <span className="text-xs text-muted">{tasks.length} tasks</span>
      </div>
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {tasks.length === 0 ? (
          <p className="text-xs text-muted text-center mt-4">No tasks</p>
        ) : (
          tasks.map(task => (
            <TaskCard key={task.id} task={task} onToggleStatus={onToggleStatus} onDelete={onDelete} />
          ))
        )}
      </div>
    </div>
  )
}
