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
        className="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-accent focus:outline-none"
      />
      <button
        type="submit"
        disabled={adding || !title.trim()}
        className="px-4 py-2 bg-accent hover:bg-blue-700 rounded text-sm text-white disabled:opacity-50 transition-colors"
      >
        {adding ? '+' : '+ Add'}
      </button>
    </form>
  )
}
