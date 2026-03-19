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
                alert.urgent ? 'bg-red-900/30 border-red-500' : 'bg-yellow-900/20 border-yellow-500'
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-white">
                    {alert.urgent ? '\u26A0 ' : '\u2709 '}{alert.subject}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">From: {alert.from}</p>
                  <p className="text-xs text-gray-300 mt-1">{alert.reason}</p>
                </div>
                <button
                  onClick={() => onDismissAlert(i)}
                  className="text-gray-500 hover:text-white text-xs ml-2"
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
        <div className="p-4 bg-surface-light rounded-lg border border-gray-700">
          <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Today's Plan</h3>
          <p className="text-sm text-gray-200 leading-relaxed">{summary}</p>

          {tasksToday.length > 0 && (
            <div className="mt-3">
              <span className="text-xs text-gray-500">Focus on: </span>
              <span className="text-xs text-gray-300">{tasksToday.join(', ')}</span>
            </div>
          )}
          {tasksLater.length > 0 && (
            <div className="mt-1">
              <span className="text-xs text-gray-500">Deferred: </span>
              <span className="text-xs text-gray-400">{tasksLater.join(', ')}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
