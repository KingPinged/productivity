import { useState } from 'react'
import Sidebar from './components/Sidebar'
import CalendarView from './components/CalendarView'
import SettingsView from './components/SettingsView'
import TasksView from './components/TasksView'

type View = 'today' | 'tasks' | 'week' | 'settings'

export default function App() {
  const [view, setView] = useState<View>('today')

  return (
    <div className="flex h-screen bg-surface">
      <Sidebar currentView={view} onNavigate={setView} />
      <main className="flex-1 overflow-auto p-6">
        {view === 'today' && <CalendarView mode="day" />}
        {view === 'week' && <CalendarView mode="week" />}
        {view === 'settings' && <SettingsView />}
        {view === 'tasks' && <TasksView />}
      </main>
    </div>
  )
}
