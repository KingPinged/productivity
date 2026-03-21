import { useState } from 'react'
import { apiFetch } from '../api/client'

interface EventModalProps {
  mode: 'create' | 'edit'
  event?: {
    id: number
    title: string
    start_time: string
    end_time: string | null
    event_type: string | null
    source: string
    description: string | null
  }
  defaultStart?: string
  defaultEnd?: string
  onClose: () => void
  onSaved: () => void
}

const EVENT_TYPES = [
  { value: 'personal', label: 'Personal', color: '#E066A0' },
  { value: 'meeting', label: 'Meeting', color: '#2EBF8B' },
  { value: 'class', label: 'Class', color: '#7577E8' },
  { value: 'study', label: 'Study', color: '#7577E8' },
  { value: 'social', label: 'Social', color: '#E5A820' },
  { value: 'health', label: 'Health', color: '#1FAD52' },
]

function formatTimeForInput(isoStr: string | undefined | null): string {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    if (!isNaN(d.getTime())) {
      return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    }
  } catch { /* fall through */ }
  if (isoStr.includes('T')) return isoStr.split('T')[1]?.slice(0, 5) || ''
  return isoStr.slice(0, 5)
}

function formatDateForInput(isoStr: string | undefined | null): string {
  if (!isoStr) return new Date().toISOString().split('T')[0]
  try {
    const d = new Date(isoStr)
    if (!isNaN(d.getTime())) {
      return d.toISOString().split('T')[0]
    }
  } catch { /* fall through */ }
  if (isoStr.includes('T')) return isoStr.split('T')[0]
  return isoStr
}

export default function EventModal({ mode, event, defaultStart, defaultEnd, onClose, onSaved }: EventModalProps) {
  const [title, setTitle] = useState(event?.title || '')
  const [date, setDate] = useState(formatDateForInput(event?.start_time || defaultStart))
  const [startTime, setStartTime] = useState(formatTimeForInput(event?.start_time || defaultStart))
  const [endTime, setEndTime] = useState(formatTimeForInput(event?.end_time || defaultEnd))
  const [eventType, setEventType] = useState(event?.event_type || 'personal')
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const handleSave = async () => {
    if (!title.trim()) return
    setSaving(true)
    try {
      const startISO = `${date}T${startTime}:00`
      const endISO = endTime ? `${date}T${endTime}:00` : undefined

      if (mode === 'create') {
        await apiFetch('/api/events', {
          method: 'POST',
          body: JSON.stringify({
            title: title.trim(),
            start_time: startISO,
            end_time: endISO,
            event_type: eventType,
          }),
        })
      } else if (event) {
        await apiFetch(`/api/events/${event.id}`, {
          method: 'PATCH',
          body: JSON.stringify({
            title: title.trim(),
            start_time: startISO,
            end_time: endISO,
            event_type: eventType,
          }),
        })
      }
      onSaved()
      onClose()
    } catch (err) {
      console.error('Failed to save event:', err)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!event) return
    setDeleting(true)
    try {
      await apiFetch(`/api/events/${event.id}`, { method: 'DELETE' })
      onSaved()
      onClose()
    } catch (err) {
      console.error('Failed to delete:', err)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-end sm:items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-surface border border-border rounded-t-2xl sm:rounded-2xl p-5 w-full sm:w-[420px] shadow-elevated max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-display font-bold text-primary">
            {mode === 'create' ? 'New Event' : 'Edit Event'}
          </h3>
          <button onClick={onClose} className="text-muted hover:text-primary text-xl p-1">
            {'\u2715'}
          </button>
        </div>

        <div className="space-y-4">
          {/* Title */}
          <div>
            <label className="block text-xs text-secondary font-medium mb-1">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Event name"
              autoFocus
              className="w-full bg-cream border border-border rounded-xl px-3 py-2.5 text-primary text-sm focus:border-accent focus:ring-1 focus:ring-accent/20 focus:outline-none"
            />
          </div>

          {/* Date */}
          <div>
            <label className="block text-xs text-secondary font-medium mb-1">Date</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full bg-cream border border-border rounded-xl px-3 py-2.5 text-primary text-sm focus:border-accent focus:outline-none"
            />
          </div>

          {/* Times */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-secondary font-medium mb-1">Start</label>
              <input
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="w-full bg-cream border border-border rounded-xl px-3 py-2.5 text-primary text-sm focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-secondary font-medium mb-1">End</label>
              <input
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="w-full bg-cream border border-border rounded-xl px-3 py-2.5 text-primary text-sm focus:border-accent focus:outline-none"
              />
            </div>
          </div>

          {/* Type */}
          <div>
            <label className="block text-xs text-secondary font-medium mb-1">Type</label>
            <div className="flex flex-wrap gap-2">
              {EVENT_TYPES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => setEventType(t.value)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    eventType === t.value
                      ? 'text-white shadow-soft'
                      : 'bg-cream border border-border text-secondary hover:text-primary'
                  }`}
                  style={eventType === t.value ? { backgroundColor: t.color } : undefined}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 mt-6">
          <button
            onClick={handleSave}
            disabled={saving || !title.trim()}
            className="flex-1 py-2.5 bg-accent hover:bg-accent-hover rounded-xl text-sm text-white font-medium disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving...' : mode === 'create' ? 'Create Event' : 'Save Changes'}
          </button>
          {mode === 'edit' && event && event.source === 'manual' && (
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="px-4 py-2.5 bg-urgent/10 hover:bg-urgent/20 rounded-xl text-sm text-urgent font-medium disabled:opacity-50 transition-colors"
            >
              {deleting ? '...' : 'Delete'}
            </button>
          )}
        </div>

        {mode === 'edit' && event && event.source !== 'manual' && (
          <p className="text-xs text-muted mt-3 text-center">
            Synced from {event.source} — delete from the source to remove
          </p>
        )}
      </div>
    </div>
  )
}
