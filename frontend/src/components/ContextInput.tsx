import { useState } from 'react'

interface ContextInputProps {
  onSubmit: (message: string) => Promise<void>
  onReplan: () => Promise<void>
}

const SUGGESTIONS = [
  "I'm skipping office hours today",
  "No class today",
  "I'm struggling in math",
  "I'm feeling burnt out",
  "I have a doctor's appointment at 2pm",
  "I need to focus on my project today",
]

export default function ContextInput({ onSubmit, onReplan }: ContextInputProps) {
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)

  const handleSubmit = async (text: string) => {
    const msg = text.trim()
    if (!msg) return
    setSending(true)
    try {
      await onSubmit(msg)
      setMessage('')
      await onReplan()
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="mb-4">
      <div className="flex gap-2">
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit(message)}
          placeholder="Tell the AI about your day... (e.g., 'I'm skipping office hours')"
          className="flex-1 bg-surface border border-border rounded-lg px-4 py-2.5 text-sm text-primary placeholder-muted focus:border-accent focus:ring-1 focus:ring-accent/20 focus:outline-none"
          disabled={sending}
        />
        <button
          onClick={() => handleSubmit(message)}
          disabled={sending || !message.trim()}
          className="px-4 py-2.5 bg-accent hover:bg-accent-hover rounded-lg text-sm text-white disabled:opacity-50 transition-colors"
        >
          {sending ? '...' : 'Update'}
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => handleSubmit(s)}
            disabled={sending}
            className="px-2.5 py-1 bg-surface hover:bg-sand border border-border rounded-full text-xs text-secondary hover:text-primary transition-colors disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
