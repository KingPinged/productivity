import { useState, useEffect } from 'react'
import { usePreferences } from '../hooks/usePreferences'
import AccountsPanel from './AccountsPanel'
import CanvasPanel from './CanvasPanel'

const FIELDS = [
  { key: 'wake_time', label: 'Wake Time', type: 'time', default: '07:00' },
  { key: 'sleep_time', label: 'Sleep Time', type: 'time', default: '23:00' },
  { key: 'max_work_hours', label: 'Max Work Hours/Day', type: 'number', default: '8' },
  { key: 'break_frequency', label: 'Break Every (min)', type: 'number', default: '90' },
  { key: 'study_block_length', label: 'Study Block Length (min)', type: 'number', default: '60' },
  { key: 'schedule_style', label: 'Schedule Style', type: 'select', default: 'balanced', options: ['packed', 'balanced', 'relaxed'] },
  { key: 'quiet_hours_start', label: 'Quiet Hours Start', type: 'time', default: '23:00' },
  { key: 'quiet_hours_end', label: 'Quiet Hours End', type: 'time', default: '07:00' },
  { key: 'nudge_enabled', label: 'Nudge System', type: 'select', default: 'enabled', options: ['enabled', 'disabled'] },
] as const

export default function SettingsView() {
  const { prefs, loading, save } = usePreferences()
  const [form, setForm] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const initial: Record<string, string> = {}
    for (const field of FIELDS) {
      initial[field.key] = prefs[field.key] || field.default
    }
    // Include API key if already set
    if (prefs['anthropic_api_key']) {
      initial['anthropic_api_key'] = prefs['anthropic_api_key']
    }
    setForm(initial)
  }, [prefs])

  const handleSave = async () => {
    setSaving(true)
    try {
      await save(form)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="text-gray-400">Loading...</div>

  return (
    <div className="max-w-lg">
      <h2 className="text-xl font-bold mb-6">Preferences</h2>

      <div className="space-y-4">
        {FIELDS.map((field) => (
          <div key={field.key}>
            <label className="block text-sm text-gray-400 mb-1">{field.label}</label>
            {field.type === 'select' ? (
              <select
                value={form[field.key] || ''}
                onChange={(e) => setForm({ ...form, [field.key]: e.target.value })}
                className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
              >
                {'options' in field && field.options.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            ) : (
              <input
                type={field.type}
                value={form[field.key] || ''}
                onChange={(e) => setForm({ ...form, [field.key]: e.target.value })}
                className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
              />
            )}
          </div>
        ))}
      </div>

      <div className="mt-6">
        <label className="block text-sm text-gray-400 mb-1">Anthropic API Key</label>
        <input
          type="password"
          value={form['anthropic_api_key'] || ''}
          onChange={(e) => setForm({ ...form, anthropic_api_key: e.target.value })}
          placeholder="sk-ant-..."
          className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white font-mono text-sm"
        />
        <p className="text-xs text-gray-500 mt-1">
          Required for AI scheduling. Restart planner after changing.
        </p>
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="mt-6 px-6 py-2 bg-accent hover:bg-blue-700 rounded text-white font-medium disabled:opacity-50 transition-colors"
      >
        {saving ? 'Saving...' : 'Save Preferences'}
      </button>

      <div className="mt-10 border-t border-gray-700 pt-6">
        <AccountsPanel />
        <p className="text-xs text-gray-500 mt-2">
          To connect Google accounts, place your Google Cloud OAuth credentials file as
          "google_client_config.json" in the app data directory, then restart the planner.
        </p>
      </div>

      <div className="mt-6 border-t border-gray-700 pt-6">
        <CanvasPanel />
      </div>
    </div>
  )
}
