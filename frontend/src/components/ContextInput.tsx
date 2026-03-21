import { useState, useRef } from 'react'
import ReactMarkdown from 'react-markdown'

interface ContextInputProps {
  onSubmit?: (message: string) => Promise<void>
  onReplan?: () => Promise<void>
  onChatDone?: () => void
  chatResponse: string | null
  setChatResponse: (v: string | null) => void
  chatActions: string | null
  setChatActions: (v: string | null) => void
}

const SUGGESTIONS = [
  "I'm skipping office hours today",
  "No class today",
  "I'm struggling in math",
  "I'm feeling burnt out",
  "What should I focus on?",
  "What are my grades?",
]

function getToken(): string {
  return (window as any).__PLANNER_TOKEN__ || ''
}

export default function ContextInput({ onChatDone, chatResponse, setChatResponse, chatActions: actions, setChatActions: setActions }: ContextInputProps) {
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const responseRef = useRef('')

  const handleSubmit = async (text: string) => {
    const msg = text.trim()
    if (!msg) return
    setSending(true)
    setStreaming(true)
    setChatResponse('')
    setActions(null)
    responseRef.current = ''
    setMessage('')

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ message: msg }),
      })

      if (!resp.ok) {
        setChatResponse('Error: Could not reach AI.')
        setStreaming(false)
        setSending(false)
        return
      }

      const reader = resp.body?.getReader()
      const decoder = new TextDecoder()

      if (reader) {
        let buffer = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            try {
              const data = JSON.parse(line.slice(6))
              if (data.type === 'actions') {
                setActions(data.text)
              } else if (data.type === 'chunk') {
                responseRef.current += data.text
                setChatResponse(responseRef.current)
              } else if (data.type === 'error') {
                responseRef.current += `\n\n*Error: ${data.text}*`
                setChatResponse(responseRef.current)
              }
            } catch {
              // ignore
            }
          }
        }
      }

      setStreaming(false)
      // Refresh calendar/tasks/summary after AI may have made changes
      onChatDone?.()
    } catch (err) {
      console.error('Failed:', err)
      setChatResponse('Something went wrong. Please try again.')
      setStreaming(false)
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
          onKeyDown={(e) => e.key === 'Enter' && !sending && handleSubmit(message)}
          placeholder="Talk to your AI planner..."
          className="flex-1 bg-surface border border-border rounded-xl px-4 py-2.5 text-sm text-primary placeholder-muted focus:border-accent focus:ring-1 focus:ring-accent/20 focus:outline-none"
          disabled={sending}
        />
        <button
          onClick={() => handleSubmit(message)}
          disabled={sending || !message.trim()}
          className="px-5 py-2.5 bg-accent hover:bg-accent-hover rounded-xl text-sm text-white disabled:opacity-50 transition-colors font-medium"
        >
          {streaming ? (
            <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : 'Send'}
        </button>
      </div>
      <div className="flex gap-1.5 mt-2 overflow-x-auto pb-1 md:flex-wrap md:overflow-visible scrollbar-hide">
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

      {(chatResponse !== null || actions) && (
        <div className="mt-3 bg-surface rounded-xl border border-border overflow-hidden">
          {/* Action indicators */}
          {actions && (
            <div className="px-4 py-2 bg-accent/5 border-b border-border flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              <span className="text-xs text-accent font-medium">{actions}</span>
            </div>
          )}

          {/* Response */}
          {chatResponse !== null && (
            <div className="p-4">
              <div className="flex items-start gap-3">
                <span className="bg-accent text-white text-[0.65rem] font-bold px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5">AI</span>
                <div className="flex-1 min-w-0 prose prose-sm prose-stone max-w-none
                  prose-headings:font-display prose-headings:text-primary prose-headings:mt-3 prose-headings:mb-1.5
                  prose-h2:text-base prose-h3:text-sm
                  prose-p:text-primary prose-p:leading-relaxed prose-p:my-1.5
                  prose-strong:text-primary prose-strong:font-semibold
                  prose-li:text-primary prose-li:my-0.5
                  prose-ul:my-1.5 prose-ol:my-1.5
                  prose-a:text-accent prose-a:no-underline hover:prose-a:underline
                ">
                  <ReactMarkdown>{chatResponse}</ReactMarkdown>
                  {streaming && (
                    <span className="inline-block w-1.5 h-4 bg-accent/50 animate-pulse ml-0.5 rounded-sm" />
                  )}
                </div>
              </div>
              {!streaming && (
                <button
                  onClick={() => { setChatResponse(null); setActions(null) }}
                  className="text-xs text-muted hover:text-secondary mt-3 ml-8"
                >
                  Dismiss
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
