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
          &#x2715;
        </button>
      </div>
    </div>
  )
}
