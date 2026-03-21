type View = 'today' | 'tasks' | 'week' | 'courses' | 'settings'

interface BottomNavProps {
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

export default function BottomNav({ currentView, onNavigate }: BottomNavProps) {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-surface border-t border-border flex justify-around items-center h-16 z-40 safe-bottom">
      {navItems.map(({ view, label, icon }) => (
        <button
          key={view}
          onClick={() => onNavigate(view)}
          className={`flex flex-col items-center gap-0.5 py-1 px-3 rounded-lg transition-colors ${
            currentView === view
              ? 'text-accent'
              : 'text-muted'
          }`}
        >
          <span className="text-lg">{icon}</span>
          <span className="text-[10px] font-medium">{label}</span>
        </button>
      ))}
    </nav>
  )
}
