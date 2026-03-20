import { useState, useRef } from 'react'
import ReactMarkdown from 'react-markdown'

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

function getToken(): string {
  return (window as any).__PLANNER_TOKEN__ || ''
}

export default function ContextInput({ onSubmit, onReplan }: ContextInputProps) {
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [chatResponse, setChatResponse] = useState<string | null>(null)
  const responseRef = useRef('')

  const handleSubmit = async (text: string) => {
    const msg = text.trim()
    if (!msg) return
    setSending(true)
    setChatResponse(null)
    responseRef.current = ''
    try {
      if (isQuestion(msg)) {
        setStreaming(true)
        setChatResponse('')
        setMessage('')

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
                if (data.type === 'chunk') {
                  responseRef.current += data.text
                  setChatResponse(responseRef.current)
                } else if (data.type === 'error') {
                  responseRef.current += `\n\n*Error: ${data.text}*`
                  setChatResponse(responseRef.current)
                }
              } catch {
                // ignore parse errors
              }
            }
          }
        }

        setStreaming(false)
      } else {
        await onSubmit(msg)
        setMessage('')
        await onReplan()
      }
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
          placeholder="Tell the AI about your day or ask a question..."
          className="flex-1 bg-surface border border-border rounded-xl px-4 py-2.5 text-sm text-primary placeholder-muted focus:border-accent focus:ring-1 focus:ring-accent/20 focus:outline-none"
          disabled={sending}
        />
        <button
          onClick={() => handleSubmit(message)}
          disabled={sending || !message.trim()}
          className="px-4 py-2.5 bg-accent hover:bg-accent-hover rounded-xl text-sm text-white disabled:opacity-50 transition-colors font-medium"
        >
          {streaming ? (
            <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : isQuestion(message) ? 'Ask' : 'Update'}
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

      {chatResponse !== null && (
        <div className="mt-3 p-4 bg-surface rounded-xl border border-border">
          <div className="flex items-start gap-3">
            <span className="bg-accent text-white text-xs font-bold px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5">AI</span>
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
                <span className="inline-block w-2 h-4 bg-accent/60 animate-pulse ml-0.5" />
              )}
            </div>
          </div>
          {!streaming && (
            <button
              onClick={() => setChatResponse(null)}
              className="text-xs text-muted hover:text-secondary mt-3 ml-8"
            >
              Dismiss
            </button>
          )}
        </div>
      )}
    </div>
  )
}
