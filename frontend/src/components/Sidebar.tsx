import { useMemo } from 'react'
import { useSchedule } from '../hooks/useSchedule'
import { useTasks } from '../hooks/useTasks'
import type { ScheduleBlock } from '../types'

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
          What&apos;s Next
        </h3>
        {nextBlock ? (
          <div className="text-sm">
            <p className="text-white font-medium">{nextBlock.block_type}</p>
            <p className="text-gray-400 text-xs">{nextBlock.start_time} &mdash; {nextBlock.end_time}</p>
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
