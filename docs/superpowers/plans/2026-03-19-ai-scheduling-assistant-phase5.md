# AI Scheduling Assistant — Phase 5: Full UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete planner UI with Tasks view (three-column kanban), schedule block rendering on the calendar, drag-drop rescheduling, block click details, What's Next sidebar panel, and a quick-add task bar.

**Architecture:** The CalendarView is upgraded to render both synced events AND AI-generated schedule blocks (merged into FullCalendar). The Tasks view uses a three-column layout (Now/Later/Future) with task cards. The Sidebar's What's Next panel shows the next upcoming schedule block. Drag-drop on the calendar triggers a PATCH to move blocks. Clicking a block opens a detail popover showing AI reasoning. A quick-add bar lets users create manual tasks inline.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, FullCalendar (drag-drop), FastAPI

**Spec:** `docs/superpowers/specs/2026-03-19-ai-scheduling-assistant-design.md` (Section 5)

**Depends on:** Phase 1-4 (all backend APIs, schedule blocks, tasks, AI scheduler)

---

## File Structure

### New Frontend Files

| File | Responsibility |
|------|---------------|
| `frontend/src/components/TasksView.tsx` | Three-column task board (Now/Later/Future) with task cards |
| `frontend/src/components/TaskCard.tsx` | Individual task card with status toggle, source icon, deadline |
| `frontend/src/components/QuickAddTask.tsx` | Inline task creation bar |
| `frontend/src/components/BlockDetail.tsx` | Popover showing schedule block details + AI reasoning |
| `frontend/src/hooks/useTasks.ts` | Task data fetching + CRUD mutations |

### Modified Frontend Files

| File | Change |
|------|--------|
| `frontend/src/App.tsx` | Replace tasks placeholder with TasksView |
| `frontend/src/components/CalendarView.tsx` | Merge schedule blocks into calendar, add drag-drop + click handlers |
| `frontend/src/components/Sidebar.tsx` | Wire What's Next panel to live schedule data |
| `frontend/src/hooks/useSchedule.ts` | Add block update mutation and replan trigger |
| `frontend/src/types/index.ts` | No changes needed — Task and ScheduleBlock types already exist |

---

## Task 1: Tasks Hook

**Files:**
- Create: `frontend/src/hooks/useTasks.ts`

- [ ] **Step 1: Create tasks hook**

Create `frontend/src/hooks/useTasks.ts`:
```typescript
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
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useTasks.ts
git commit -m "feat(frontend): add useTasks hook for task CRUD operations"
```

---

## Task 2: Upgrade useSchedule Hook

**Files:**
- Modify: `frontend/src/hooks/useSchedule.ts`

- [ ] **Step 1: Add block update and replan to useSchedule**

Replace `frontend/src/hooks/useSchedule.ts`:
```typescript
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
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useSchedule.ts
git commit -m "feat(frontend): add block update and replan to useSchedule hook"
```

---

## Task 3: Task Card Component

**Files:**
- Create: `frontend/src/components/TaskCard.tsx`

- [ ] **Step 1: Create TaskCard**

Create `frontend/src/components/TaskCard.tsx`:
```tsx
import type { Task } from '../types'

const SOURCE_ICONS: Record<string, string> = {
  canvas: '\u{1F393}',
  gmail: '\u2709',
  manual: '\u270F',
}

const PRIORITY_COLORS: Record<number, string> = {
  1: 'bg-red-500',
  2: 'bg-orange-500',
  3: 'bg-blue-500',
  4: 'bg-gray-500',
  5: 'bg-gray-600',
}

interface TaskCardProps {
  task: Task
  onToggleStatus: (taskId: number, newStatus: string) => void
  onDelete: (taskId: number) => void
}

export default function TaskCard({ task, onToggleStatus, onDelete }: TaskCardProps) {
  const isDone = task.status === 'done'
  const sourceIcon = SOURCE_ICONS[task.source] || '\u2022'

  const formatDeadline = (deadline: string | null) => {
    if (!deadline) return null
    const d = new Date(deadline)
    const now = new Date()
    const diffMs = d.getTime() - now.getTime()
    const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24))

    if (diffDays < 0) return { text: 'Overdue', color: 'text-red-400' }
    if (diffDays === 0) return { text: 'Due today', color: 'text-red-400' }
    if (diffDays === 1) return { text: 'Due tomorrow', color: 'text-orange-400' }
    if (diffDays <= 3) return { text: `Due in ${diffDays} days`, color: 'text-yellow-400' }
    return { text: d.toLocaleDateString(), color: 'text-gray-400' }
  }

  const deadline = formatDeadline(task.deadline)

  return (
    <div className={`p-3 bg-gray-800 rounded-lg border border-gray-700 ${isDone ? 'opacity-50' : ''}`}>
      <div className="flex items-start gap-2">
        <button
          onClick={() => onToggleStatus(task.id, isDone ? 'pending' : 'done')}
          className={`mt-0.5 w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center text-xs ${
            isDone ? 'bg-green-600 border-green-600 text-white' : 'border-gray-500 hover:border-gray-300'
          }`}
        >
          {isDone ? '\u2713' : ''}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-xs">{sourceIcon}</span>
            <span className={`text-sm font-medium ${isDone ? 'line-through text-gray-500' : 'text-white'}`}>
              {task.title}
            </span>
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${PRIORITY_COLORS[task.priority] || 'bg-gray-500'}`} />
          </div>

          <div className="flex items-center gap-2 mt-1 text-xs">
            {task.course && <span className="text-gray-400">{task.course}</span>}
            {task.estimated_minutes && <span className="text-gray-500">~{task.estimated_minutes}m</span>}
            {deadline && <span className={deadline.color}>{deadline.text}</span>}
            {task.current_grade && <span className="text-gray-500">Grade: {task.current_grade}</span>}
          </div>
        </div>

        <button
          onClick={() => onDelete(task.id)}
          className="text-gray-600 hover:text-red-400 text-xs flex-shrink-0"
        >
          \u2715
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/TaskCard.tsx
git commit -m "feat(frontend): add TaskCard component with status toggle and deadline display"
```

---

## Task 4: Quick Add Task Bar

**Files:**
- Create: `frontend/src/components/QuickAddTask.tsx`

- [ ] **Step 1: Create QuickAddTask**

Create `frontend/src/components/QuickAddTask.tsx`:
```tsx
import { useState } from 'react'

interface QuickAddTaskProps {
  onAdd: (task: { title: string; deadline?: string }) => Promise<number>
}

export default function QuickAddTask({ onAdd }: QuickAddTaskProps) {
  const [title, setTitle] = useState('')
  const [adding, setAdding] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    setAdding(true)
    try {
      await onAdd({ title: title.trim() })
      setTitle('')
    } finally {
      setAdding(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 mb-4">
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Add a task..."
        className="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-accent focus:outline-none"
      />
      <button
        type="submit"
        disabled={adding || !title.trim()}
        className="px-4 py-2 bg-accent hover:bg-blue-700 rounded text-sm text-white disabled:opacity-50 transition-colors"
      >
        {adding ? '+' : '+ Add'}
      </button>
    </form>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/QuickAddTask.tsx
git commit -m "feat(frontend): add QuickAddTask inline creation bar"
```

---

## Task 5: Tasks View (Three-Column Board)

**Files:**
- Create: `frontend/src/components/TasksView.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create TasksView**

Create `frontend/src/components/TasksView.tsx`:
```tsx
import { useMemo, useCallback } from 'react'
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

export default function TasksView() {
  const { tasks, loading, addTask, updateStatus, deleteTask } = useTasks(undefined, 'pending')
  const today = new Date().toISOString().split('T')[0]
  const { triggerReplan } = useSchedule(today)

  // Wrap updateStatus to trigger replan when a task is completed
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

  if (loading) return <div className="text-gray-400">Loading tasks...</div>

  return (
    <div className="h-full flex flex-col">
      <QuickAddTask onAdd={addTask} />

      <div className="flex-1 grid grid-cols-3 gap-4 min-h-0">
        <TaskColumn
          title="Now"
          subtitle="Due today/tomorrow"
          tasks={columns.now}
          accentColor="text-red-400"
          onToggleStatus={handleToggleStatus}
          onDelete={deleteTask}
        />
        <TaskColumn
          title="Later"
          subtitle="This week"
          tasks={columns.later}
          accentColor="text-yellow-400"
          onToggleStatus={handleToggleStatus}
          onDelete={deleteTask}
        />
        <TaskColumn
          title="Future"
          subtitle="Beyond this week"
          tasks={columns.future}
          accentColor="text-blue-400"
          onToggleStatus={handleToggleStatus}
          onDelete={deleteTask}
        />
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
        <h3 className={`text-sm font-bold uppercase ${accentColor}`}>{title}</h3>
        <p className="text-xs text-gray-500">{subtitle}</p>
        <span className="text-xs text-gray-600">{tasks.length} tasks</span>
      </div>
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {tasks.length === 0 ? (
          <p className="text-xs text-gray-600 text-center mt-4">No tasks</p>
        ) : (
          tasks.map(task => (
            <TaskCard
              key={task.id}
              task={task}
              onToggleStatus={onToggleStatus}
              onDelete={onDelete}
            />
          ))
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Update App.tsx to use TasksView**

Replace the tasks placeholder in `frontend/src/App.tsx`:

Change:
```tsx
{view === 'tasks' && (
  <div className="text-gray-400 text-center mt-20">
    Tasks view — coming in Phase 5
  </div>
)}
```

To:
```tsx
{view === 'tasks' && <TasksView />}
```

Add import at top:
```tsx
import TasksView from './components/TasksView'
```

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add three-column Tasks view with quick-add bar"
```

---

## Task 6: Block Detail Popover

**Files:**
- Create: `frontend/src/components/BlockDetail.tsx`

- [ ] **Step 1: Create BlockDetail**

Create `frontend/src/components/BlockDetail.tsx`:
```tsx
import type { ScheduleBlock } from '../types'

const BLOCK_TYPE_LABELS: Record<string, string> = {
  study: 'Study',
  meeting: 'Meeting',
  rest: 'Break',
  personal: 'Personal',
  buffer: 'Buffer',
}

interface BlockDetailProps {
  block: ScheduleBlock
  onClose: () => void
  onComplete: (blockId: number) => void
  onSkip: (blockId: number) => void
}

export default function BlockDetail({ block, onClose, onComplete, onSkip }: BlockDetailProps) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-surface-light border border-gray-700 rounded-xl p-5 w-96 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white">
            {BLOCK_TYPE_LABELS[block.block_type] || block.block_type}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-lg">
            {'\u2715'}
          </button>
        </div>

        <div className="space-y-3 text-sm">
          <div>
            <span className="text-gray-400">Time: </span>
            <span className="text-white">{block.start_time} — {block.end_time}</span>
          </div>

          <div>
            <span className="text-gray-400">Status: </span>
            <span className={`font-medium ${
              block.status === 'completed' ? 'text-green-400' :
              block.status === 'skipped' ? 'text-gray-500' :
              'text-blue-400'
            }`}>
              {block.status}
            </span>
          </div>

          {block.ai_reason && (
            <div>
              <span className="text-gray-400">AI Reasoning: </span>
              <span className="text-gray-300 italic">{block.ai_reason}</span>
            </div>
          )}
        </div>

        {block.status === 'scheduled' && (
          <div className="flex gap-2 mt-5">
            <button
              onClick={() => onComplete(block.id)}
              className="flex-1 py-2 bg-green-600 hover:bg-green-700 rounded text-sm text-white transition-colors"
            >
              Mark Complete
            </button>
            <button
              onClick={() => onSkip(block.id)}
              className="flex-1 py-2 bg-gray-600 hover:bg-gray-700 rounded text-sm text-white transition-colors"
            >
              Skip
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/BlockDetail.tsx
git commit -m "feat(frontend): add BlockDetail popover with AI reasoning and status actions"
```

---

## Task 7: Upgrade CalendarView with Schedule Blocks + Interactions

**Files:**
- Modify: `frontend/src/components/CalendarView.tsx`

- [ ] **Step 1: Rewrite CalendarView**

Replace `frontend/src/components/CalendarView.tsx`:
```tsx
import { useMemo, useState, useCallback } from 'react'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import { useEvents } from '../hooks/useEvents'
import { useSchedule } from '../hooks/useSchedule'
import BlockDetail from './BlockDetail'
import type { CalendarEvent, ScheduleBlock } from '../types'

interface CalendarViewProps {
  mode: 'day' | 'week'
}

const SOURCE_COLORS: Record<string, string> = {
  gcal: '#22c55e',
  gmail: '#3b82f6',
  canvas: '#f59e0b',
  manual: '#a855f7',
}

const BLOCK_COLORS: Record<string, string> = {
  study: '#3b82f6',
  meeting: '#22c55e',
  rest: '#f59e0b',
  personal: '#a855f7',
  buffer: '#6b7280',
}

function toFullCalendarEvent(event: CalendarEvent) {
  return {
    id: `event-${event.id}`,
    title: event.title,
    start: event.start_time,
    end: event.end_time || undefined,
    allDay: event.all_day,
    backgroundColor: SOURCE_COLORS[event.source] || '#6b7280',
    borderColor: SOURCE_COLORS[event.source] || '#6b7280',
    extendedProps: { type: 'event', source: event.source },
  }
}

function blockToFullCalendar(block: ScheduleBlock) {
  // Convert HH:MM to full ISO for today
  const date = block.date
  return {
    id: `block-${block.id}`,
    title: `${block.block_type.charAt(0).toUpperCase() + block.block_type.slice(1)}${block.ai_reason ? `: ${block.ai_reason}` : ''}`,
    start: `${date}T${block.start_time}:00`,
    end: `${date}T${block.end_time}:00`,
    backgroundColor: block.status === 'completed' ? '#374151' : (BLOCK_COLORS[block.block_type] || '#6b7280'),
    borderColor: block.status === 'completed' ? '#4b5563' : (BLOCK_COLORS[block.block_type] || '#6b7280'),
    textColor: block.status === 'completed' ? '#9ca3af' : '#ffffff',
    extendedProps: { type: 'block', block },
  }
}

export default function CalendarView({ mode }: CalendarViewProps) {
  const initialView = mode === 'day' ? 'timeGridDay' : 'timeGridWeek'
  const today = new Date().toISOString().split('T')[0]
  const { events } = useEvents()
  const { schedule, updateBlock, triggerReplan } = useSchedule(today)
  const [selectedBlock, setSelectedBlock] = useState<ScheduleBlock | null>(null)

  const calendarEvents = useMemo(() => {
    const eventItems = events.map(toFullCalendarEvent)
    const blockItems = (schedule?.blocks || []).map(blockToFullCalendar)
    return [...eventItems, ...blockItems]
  }, [events, schedule])

  const handleEventClick = useCallback((info: any) => {
    const props = info.event.extendedProps
    if (props.type === 'block' && props.block) {
      setSelectedBlock(props.block)
    }
  }, [])

  const handleEventDrop = useCallback(async (info: any) => {
    const props = info.event.extendedProps
    if (props.type !== 'block' || !props.block) {
      info.revert()
      return
    }
    // Update the block's time then trigger AI replan
    try {
      const newStart = info.event.start?.toTimeString().slice(0, 5) || props.block.start_time
      const newEnd = info.event.end?.toTimeString().slice(0, 5) || props.block.end_time
      await updateBlock(props.block.id, { start_time: newStart, end_time: newEnd })
      await triggerReplan()
    } catch {
      info.revert()
    }
  }, [updateBlock, triggerReplan])

  const handleComplete = useCallback(async (blockId: number) => {
    await updateBlock(blockId, { status: 'completed' })
    setSelectedBlock(null)
  }, [updateBlock])

  const handleSkip = useCallback(async (blockId: number) => {
    await updateBlock(blockId, { status: 'skipped' })
    setSelectedBlock(null)
  }, [updateBlock])

  return (
    <div className="h-full">
      <FullCalendar
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView={initialView}
        headerToolbar={{
          left: 'prev,next today',
          center: 'title',
          right: 'timeGridDay,timeGridWeek',
        }}
        editable={mode === 'day'}
        selectable={mode === 'day'}
        nowIndicator={true}
        slotMinTime="06:00:00"
        slotMaxTime="24:00:00"
        height="100%"
        events={calendarEvents}
        eventClick={handleEventClick}
        eventDrop={handleEventDrop}
      />

      {selectedBlock && (
        <BlockDetail
          block={selectedBlock}
          onClose={() => setSelectedBlock(null)}
          onComplete={handleComplete}
          onSkip={handleSkip}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CalendarView.tsx
git commit -m "feat(frontend): merge schedule blocks into calendar with click details and status actions"
```

---

## Task 8: Upgrade Sidebar What's Next Panel

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Wire What's Next to live data**

Replace `frontend/src/components/Sidebar.tsx`:
```tsx
import { useMemo } from 'react'
import { useSchedule } from '../hooks/useSchedule'
import { useTasks } from '../hooks/useTasks'
import type { ScheduleBlock, Task } from '../types'

type View = 'today' | 'tasks' | 'week' | 'settings'

interface SidebarProps {
  currentView: View
  onNavigate: (view: View) => void
}

const navItems: { view: View; label: string; icon: string }[] = [
  { view: 'today', label: 'Today', icon: '\u2600' },
  { view: 'tasks', label: 'Tasks', icon: '\u2611' },
  { view: 'week', label: 'Week', icon: '\u{1F4C5}' },
  { view: 'settings', label: 'Settings', icon: '\u2699' },
]

function getNextBlock(blocks: ScheduleBlock[]): ScheduleBlock | null {
  const now = new Date()
  const currentTime = now.toTimeString().slice(0, 5) // HH:MM

  for (const block of blocks) {
    if (block.status === 'scheduled' && block.start_time >= currentTime) {
      return block
    }
  }
  return null
}

export default function Sidebar({ currentView, onNavigate }: SidebarProps) {
  const today = new Date().toISOString().split('T')[0]
  const { schedule } = useSchedule(today)
  const { tasks } = useTasks(undefined, 'pending')

  const nextBlock = useMemo(
    () => getNextBlock(schedule?.blocks || []),
    [schedule]
  )

  const upcomingTasks = useMemo(() => {
    return tasks
      .filter(t => t.deadline)
      .sort((a, b) => (a.deadline || '').localeCompare(b.deadline || ''))
      .slice(0, 3)
  }, [tasks])

  return (
    <aside className="w-56 bg-surface-light flex flex-col border-r border-gray-700">
      <div className="p-4 border-b border-gray-700">
        <h1 className="text-lg font-bold text-white">Planner</h1>
      </div>

      <nav className="flex-1 p-2 space-y-1">
        {navItems.map(({ view, label, icon }) => (
          <button
            key={view}
            onClick={() => onNavigate(view)}
            className={`w-full text-left px-3 py-2 rounded-lg flex items-center gap-2 transition-colors ${
              currentView === view
                ? 'bg-accent text-white'
                : 'text-gray-400 hover:bg-gray-700 hover:text-gray-200'
            }`}
          >
            <span>{icon}</span>
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="p-4 border-t border-gray-700">
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">
          What's Next
        </h3>
        {nextBlock ? (
          <div className="text-sm">
            <p className="text-white font-medium">{nextBlock.block_type}</p>
            <p className="text-gray-400 text-xs">{nextBlock.start_time} — {nextBlock.end_time}</p>
            {nextBlock.ai_reason && (
              <p className="text-gray-500 text-xs mt-1 italic">{nextBlock.ai_reason}</p>
            )}
          </div>
        ) : (
          <p className="text-sm text-gray-400">No upcoming blocks</p>
        )}

        {upcomingTasks.length > 0 && (
          <>
            <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2 mt-4">
              Upcoming
            </h3>
            <div className="space-y-1">
              {upcomingTasks.map(task => (
                <div key={task.id} className="text-xs">
                  <p className="text-gray-300 truncate">{task.title}</p>
                  {task.deadline && (
                    <p className="text-gray-500">
                      {new Date(task.deadline).toLocaleDateString()}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </aside>
  )
}
```

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Sidebar.tsx
git commit -m "feat(frontend): wire What's Next panel to live schedule and task data"
```

---

## Task 9: Final Build and Test

- [ ] **Step 1: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 2: Run all Python tests**

Run: `python -m pytest tests/planner/ -v`
Expected: All 120 tests pass (no Python changes in this phase)

- [ ] **Step 3: Commit built frontend**

```bash
git add frontend/dist/
git commit -m "chore: rebuild frontend with full Phase 5 UI"
```
