interface DaySummaryProps {
  summary: string | null
  emailAlerts: { subject: string; from: string; reason: string; urgent: boolean }[]
  tasksToday: string[]
  tasksLater: string[]
  onDismissAlert: (index: number) => void
}

export default function DaySummary({ summary, emailAlerts, tasksToday, tasksLater, onDismissAlert }: DaySummaryProps) {
  if (!summary && emailAlerts.length === 0) return null

  return (
    <div className="mb-4 space-y-3">
      {/* Email Alerts */}
      {emailAlerts.length > 0 && (
        <div className="space-y-2">
          {emailAlerts.map((alert, i) => (
            <div
              key={i}
              className={`p-3 rounded-lg border-l-4 ${
                alert.urgent ? 'bg-red-50 border-urgent' : 'bg-amber-50 border-amber-400'
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-primary">
                    {alert.urgent ? '\u26A0 ' : '\u2709 '}{alert.subject}
                  </p>
                  <p className="text-xs text-secondary mt-0.5">From: {alert.from}</p>
                  <p className="text-xs text-primary mt-1">{alert.reason}</p>
                </div>
                <button
                  onClick={() => onDismissAlert(i)}
                  className="text-muted hover:text-primary text-xs ml-2"
                >
                  {'\u2715'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Daily Summary */}
      {summary && (
        <div className="p-4 bg-white rounded-xl border border-border shadow-soft">
          <h3 className="font-display font-semibold text-xs text-muted uppercase tracking-wider mb-2">Today's Plan</h3>
          <p className="text-sm text-primary leading-relaxed">{summary}</p>

          {tasksToday.length > 0 && (
            <div className="mt-3">
              <span className="text-xs text-secondary">Focus on: </span>
              <span className="text-xs text-primary">{tasksToday.join(', ')}</span>
            </div>
          )}
          {tasksLater.length > 0 && (
            <div className="mt-1">
              <span className="text-xs text-secondary">Deferred: </span>
              <span className="text-xs text-muted">{tasksLater.join(', ')}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
