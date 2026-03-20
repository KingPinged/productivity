import { useState, useCallback } from 'react'
import { hasToken } from './api/client'
import LoginPage from './components/LoginPage'
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
  const [loggedIn, setLoggedIn] = useState(hasToken())
  const [view, setView] = useState<View>('today')
  const today = new Date().toISOString().split('T')[0]
  const { addMessage } = useUserContext()
  const { summary, email_alerts, tasks_today, tasks_later, reload: reloadSummary } = useSummary(today)
  const { triggerReplan } = useSchedule(today)
  const [dismissedAlerts, setDismissedAlerts] = useState<Set<number>>(new Set())
  const [refreshKey, setRefreshKey] = useState(0)
  const [chatResponse, setChatResponse] = useState<string | null>(null)
  const [chatActions, setChatActions] = useState<string | null>(null)

  const handleReplan = useCallback(async () => {
    await triggerReplan()
    await reloadSummary()
  }, [triggerReplan, reloadSummary])

  const handleChatDone = useCallback(() => {
    // Increment key to force calendar/schedule/tasks to re-fetch
    setRefreshKey(k => k + 1)
    reloadSummary()
  }, [reloadSummary])

  const activeAlerts = email_alerts.filter((_: any, i: number) => !dismissedAlerts.has(i))

  if (!loggedIn) {
    return <LoginPage onLogin={() => setLoggedIn(true)} />
  }

  return (
    <div className="flex h-screen bg-cream font-body">
      <Sidebar currentView={view} onNavigate={setView} />
      <main className="flex-1 overflow-auto">
        {view === 'today' && (
          <div className="h-full flex flex-col">
            <div className="px-8 pt-6 pb-2">
              <h1 className="font-display font-bold text-2xl text-primary mb-1">
                {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
              </h1>
              <p className="text-secondary text-sm mb-5">Plan your day, stay on track</p>
              <ContextInput onSubmit={addMessage} onReplan={handleReplan} onChatDone={handleChatDone} chatResponse={chatResponse} setChatResponse={setChatResponse} chatActions={chatActions} setChatActions={setChatActions} />
              <DaySummary
                summary={summary}
                emailAlerts={activeAlerts}
                tasksToday={tasks_today}
                tasksLater={tasks_later}
                onDismissAlert={(i: number) => setDismissedAlerts(prev => new Set(prev).add(i))}
              />
            </div>
            <div className="flex-1 min-h-0 px-8 pb-6">
              <div className="h-full bg-surface rounded-2xl shadow-soft border border-border overflow-hidden">
                <CalendarView mode="day" key={`day-${refreshKey}`} />
              </div>
            </div>
          </div>
        )}
        {view === 'week' && (
          <div className="h-full p-8">
            <h1 className="font-display font-bold text-2xl text-primary mb-6">Week Overview</h1>
            <div className="h-[calc(100%-3.5rem)] bg-surface rounded-2xl shadow-soft border border-border overflow-hidden">
              <CalendarView mode="week" key={`week-${refreshKey}`} />
            </div>
          </div>
        )}
        {view === 'settings' && (
          <div className="p-8">
            <h1 className="font-display font-bold text-2xl text-primary mb-6">Settings</h1>
            <SettingsView />
          </div>
        )}
        {view === 'tasks' && (
          <div className="h-full p-8">
            <h1 className="font-display font-bold text-2xl text-primary mb-6">Tasks</h1>
            <TasksView key={`tasks-${refreshKey}`} />
          </div>
        )}
        {view === 'courses' && (
          <div className="h-full p-8">
            <CoursesView />
          </div>
        )}
      </main>
      <ReminderToast />
    </div>
  )
}
