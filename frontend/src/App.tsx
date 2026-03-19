import { useState, useCallback } from 'react'
import Sidebar from './components/Sidebar'
import CalendarView from './components/CalendarView'
import SettingsView from './components/SettingsView'
import TasksView from './components/TasksView'
import CoursesView from './components/CoursesView'
import ContextInput from './components/ContextInput'
import DaySummary from './components/DaySummary'
import ReminderToast from './components/ReminderToast'
import { useUserContext } from './hooks/useUserContext'
import { useSummary } from './hooks/useSummary'
import { useSchedule } from './hooks/useSchedule'

type View = 'today' | 'tasks' | 'week' | 'courses' | 'settings'

export default function App() {
  const [view, setView] = useState<View>('today')
  const today = new Date().toISOString().split('T')[0]
  const { addMessage } = useUserContext()
  const { summary, email_alerts, tasks_today, tasks_later, reload: reloadSummary } = useSummary(today)
  const { triggerReplan } = useSchedule(today)
  const [dismissedAlerts, setDismissedAlerts] = useState<Set<number>>(new Set())

  const handleReplan = useCallback(async () => {
    await triggerReplan()
    await reloadSummary()
  }, [triggerReplan, reloadSummary])

  const activeAlerts = email_alerts.filter((_, i) => !dismissedAlerts.has(i))

  return (
    <div className="flex h-screen bg-surface">
      <Sidebar currentView={view} onNavigate={setView} />
      <main className="flex-1 overflow-auto p-6">
        {view === 'today' && (
          <div className="h-full flex flex-col">
            <ContextInput onSubmit={addMessage} onReplan={handleReplan} />
            <DaySummary
              summary={summary}
              emailAlerts={activeAlerts}
              tasksToday={tasks_today}
              tasksLater={tasks_later}
              onDismissAlert={(i) => setDismissedAlerts(prev => new Set(prev).add(i))}
            />
            <div className="flex-1 min-h-0">
              <CalendarView mode="day" />
            </div>
          </div>
        )}
        {view === 'week' && <CalendarView mode="week" />}
        {view === 'settings' && <SettingsView />}
        {view === 'tasks' && <TasksView />}
        {view === 'courses' && <CoursesView />}
      </main>
      <ReminderToast />
    </div>
  )
}
