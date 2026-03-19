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

export default function Sidebar({ currentView, onNavigate }: SidebarProps) {
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
          What's Next
        </h3>
        <p className="text-sm text-gray-400">
          No tasks scheduled yet
        </p>
      </div>
    </aside>
  )
}
