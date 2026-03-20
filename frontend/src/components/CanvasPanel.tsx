import { useState } from 'react'
import { useCanvas } from '../hooks/useCanvas'

const STATUS_COLORS: Record<string, string> = {
  active: 'text-success',
  expired: 'text-amber-500',
  error: 'text-urgent',
}

export default function CanvasPanel() {
  const { configs, loading, setup, relogin, remove } = useCanvas()
  const [url, setUrl] = useState('')
  const [setting_up, setSettingUp] = useState(false)

  const handleSetup = async () => {
    if (!url.trim()) return
    setSettingUp(true)
    try {
      await setup(url.trim())
      setUrl('')
    } finally {
      setSettingUp(false)
    }
  }

  if (loading) return <div className="text-muted">Loading Canvas configs...</div>

  return (
    <div>
      <h3 className="font-display font-bold text-lg text-primary mb-4">Canvas LMS</h3>

      {configs.length === 0 ? (
        <p className="text-sm text-secondary mb-4">
          No Canvas instance connected. Enter your Canvas URL below to get started.
        </p>
      ) : (
        <div className="space-y-2 mb-4">
          {configs.map((config) => (
            <div
              key={config.id}
              className="flex items-center justify-between p-4 bg-sand rounded-xl"
            >
              <div>
                <p className="text-primary text-sm font-medium">{config.canvas_url}</p>
                <p className="text-xs text-secondary">
                  Status: <span className={STATUS_COLORS[config.status] || 'text-muted'}>
                    {config.status}
                  </span>
                  {config.last_sync && ` · Last synced: ${new Date(config.last_sync).toLocaleString()}`}
                </p>
              </div>
              <div className="flex gap-2">
                {config.status === 'expired' && (
                  <button
                    onClick={() => relogin(config.id)}
                    className="text-accent hover:text-accent-hover text-sm transition-colors"
                  >
                    Re-login
                  </button>
                )}
                <button
                  onClick={() => remove(config.id)}
                  className="text-urgent/60 hover:text-urgent text-sm transition-colors"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://canvas.university.edu"
          className="flex-1 bg-surface border border-border rounded-lg px-3 py-2 text-primary text-sm focus:border-accent focus:ring-1 focus:ring-accent/20 focus:outline-none"
        />
        <button
          onClick={handleSetup}
          disabled={setting_up || !url.trim()}
          className="px-4 py-2 bg-accent hover:bg-accent-hover text-white rounded-lg text-sm disabled:opacity-50 transition-colors"
        >
          {setting_up ? 'Logging in...' : 'Connect'}
        </button>
      </div>
      <p className="text-xs text-muted mt-2">
        A browser window will open for you to log in. Supports SSO and MFA.
      </p>
    </div>
  )
}
