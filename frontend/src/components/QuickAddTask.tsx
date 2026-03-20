import { useState } from 'react'

interface QuickAddTaskProps {
  onAdd: (task: { title: string; deadline?: string }) => Promise<number>
}

export default function QuickAddTask({ onAdd }: QuickAddTaskProps) {
  const [title, setTitle] = useState('')
  const [adding, setAdding] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    setAdding(true)
    try {
      await onAdd({ title: title.trim() })
      setTitle('')
    } finally {
      setAdding(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 mb-4">
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Add a task..."
        className="flex-1 bg-surface border border-border rounded-xl px-3 py-2 text-sm text-primary placeholder-muted focus:border-accent focus:ring-1 focus:ring-accent/20 focus:outline-none"
      />
      <button
        type="submit"
        disabled={adding || !title.trim()}
        className="px-4 py-2 bg-accent hover:bg-accent-hover text-white rounded-xl text-sm disabled:opacity-50 transition-colors"
      >
        {adding ? '+' : '+ Add'}
      </button>
    </form>
  )
}
