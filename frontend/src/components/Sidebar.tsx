import { useMemo } from 'react'
import { useSchedule } from '../hooks/useSchedule'
import { useTasks } from '../hooks/useTasks'
import type { ScheduleBlock, Task } from '../types'

type View = 'today' | 'tasks' | 'week' | 'courses' | 'settings'

interface SidebarProps {
  currentView: View
  onNavigate: (view: View) => void
}

const navItems: { view: View; label: string; icon: string }[] = [
  { view: 'today', label: 'Today', icon: '\u2600' },
  { view: 'tasks', label: 'Tasks', icon: '\u2611' },
  { view: 'week', label: 'Week', icon: '\u{1F4C5}' },
  { view: 'courses', label: 'Courses', icon: '\u{1F393}' },
  { view: 'settings', label: 'Settings', icon: '\u2699' },
]

function getNextBlock(blocks: ScheduleBlock[]): ScheduleBlock | null {
  const currentTime = new Date().toTimeString().slice(0, 5)
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
      .filter((t: Task) => t.deadline)
      .sort((a: Task, b: Task) => (a.deadline || '').localeCompare(b.deadline || ''))
      .slice(0, 3)
  }, [tasks])

  return (
    <aside className="w-60 bg-sand flex flex-col border-r border-border h-full">
      <div className="px-5 pt-6 pb-4">
        <h1 className="font-display font-extrabold text-lg text-primary tracking-tight">
          Planner
        </h1>
      </div>

      <nav className="flex-1 px-3 space-y-0.5">
        {navItems.map(({ view, label, icon }) => (
          <button
            key={view}
            onClick={() => onNavigate(view)}
            className={`w-full text-left px-3 py-2 rounded-lg flex items-center gap-2.5 transition-all duration-150 text-sm font-medium ${
              currentView === view
                ? 'bg-accent text-white shadow-soft'
                : 'text-secondary hover:bg-white hover:text-primary hover:shadow-soft'
            }`}
          >
            <span className="text-base">{icon}</span>
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="px-4 py-5 border-t border-border">
        <h3 className="font-display font-semibold text-[0.65rem] text-muted uppercase tracking-widest mb-3">
          Up Next
        </h3>
        {nextBlock ? (
          <div className="bg-white rounded-xl p-3 shadow-soft border border-border">
            <p className="text-primary text-sm font-semibold">{nextBlock.block_type}</p>
            <p className="text-secondary text-xs mt-0.5">{nextBlock.start_time} - {nextBlock.end_time}</p>
            {nextBlock.ai_reason && (
              <p className="text-muted text-xs mt-1.5 leading-relaxed">{nextBlock.ai_reason}</p>
            )}
          </div>
        ) : (
          <p className="text-muted text-xs">Nothing scheduled</p>
        )}

        {upcomingTasks.length > 0 && (
          <div className="mt-4">
            <h3 className="font-display font-semibold text-[0.65rem] text-muted uppercase tracking-widest mb-2">
              Upcoming
            </h3>
            <div className="space-y-1.5">
              {upcomingTasks.map((task: Task) => (
                <div key={task.id} className="text-xs">
                  <p className="text-primary font-medium truncate">{task.title}</p>
                  {task.deadline && (
                    <p className="text-muted">
                      {new Date(task.deadline).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}
