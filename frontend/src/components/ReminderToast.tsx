import { useReminders } from '../hooks/useReminders'

const TYPE_COLORS: Record<string, string> = {
  event: 'border-success',
  task_start: 'border-accent',
  deadline: 'border-urgent',
  break: 'border-amber-400',
  nudge: 'border-personal',
  summary: 'border-border',
}

const TYPE_ICONS: Record<string, string> = {
  event: '\u{1F4C5}',
  task_start: '\u25B6',
  deadline: '\u26A0',
  break: '\u2615',
  nudge: '\u{1F914}',
  summary: '\u2600',
}

export default function ReminderToast() {
  const { reminders, dismiss } = useReminders()

  if (reminders.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
      {reminders.map(reminder => (
        <div
          key={reminder.id}
          className={`bg-surface border border-border border-l-4 ${TYPE_COLORS[reminder.reminder_type] || 'border-border'} rounded-xl p-4 shadow-elevated animate-pulse-once`}
        >
          <div className="flex items-start gap-3">
            <span className="text-lg flex-shrink-0">
              {TYPE_ICONS[reminder.reminder_type] || '\u{1F514}'}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-primary text-sm font-medium">{reminder.message}</p>
              <p className="text-secondary text-xs mt-1">
                {new Date(reminder.remind_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>
            <button
              onClick={() => dismiss(reminder.id)}
              className="text-muted hover:text-primary text-sm flex-shrink-0"
            >
              {'\u2715'}
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
