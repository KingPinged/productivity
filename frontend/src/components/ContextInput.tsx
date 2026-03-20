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
  "What should I focus on?",
  "What did I miss yesterday?",
]

function isQuestion(text: string): boolean {
  const lower = text.toLowerCase().trim()
  return lower.endsWith('?') ||
    lower.startsWith('what') || lower.startsWith('when') ||
    lower.startsWith('how') || lower.startsWith('why') ||
    lower.startsWith('where') || lower.startsWith('who') ||
    lower.startsWith('can ') || lower.startsWith('should') ||
    lower.startsWith('do i') || lower.startsWith('am i') ||
    lower.startsWith('tell me') || lower.startsWith('show me')
}

export default function ContextInput({ onSubmit, onReplan }: ContextInputProps) {
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [chatResponse, setChatResponse] = useState<string | null>(null)

  const handleSubmit = async (text: string) => {
    const msg = text.trim()
    if (!msg) return
    setSending(true)
    setChatResponse(null)
    try {
      if (isQuestion(msg)) {
        // Send to chat endpoint
        const { apiFetch } = await import('../api/client')
        const result = await apiFetch<{ response: string }>('/api/chat', {
          method: 'POST',
          body: JSON.stringify({ message: msg }),
        })
        setChatResponse(result.response)
      } else {
        // Send as context and replan
        await onSubmit(msg)
        await onReplan()
      }
      setMessage('')
    } catch (err) {
      console.error('Failed:', err)
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
          placeholder="Tell the AI about your day or ask a question..."
          className="flex-1 bg-surface border border-border rounded-xl px-4 py-2.5 text-sm text-primary placeholder-muted focus:border-accent focus:ring-1 focus:ring-accent/20 focus:outline-none"
          disabled={sending}
        />
        <button
          onClick={() => handleSubmit(message)}
          disabled={sending || !message.trim()}
          className="px-4 py-2.5 bg-accent hover:bg-accent-hover rounded-xl text-sm text-white disabled:opacity-50 transition-colors font-medium"
        >
          {sending ? '...' : isQuestion(message) ? 'Ask' : 'Update'}
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

      {chatResponse && (
        <div className="mt-3 p-4 bg-surface rounded-xl border border-border">
          <div className="flex items-start gap-2">
            <span className="text-accent font-bold text-sm flex-shrink-0">AI</span>
            <p className="text-sm text-primary leading-relaxed whitespace-pre-wrap">{chatResponse}</p>
          </div>
          <button
            onClick={() => setChatResponse(null)}
            className="text-xs text-muted hover:text-secondary mt-2"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  )
}
