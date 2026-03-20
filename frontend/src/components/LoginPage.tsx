import { useState } from 'react'
import { setToken } from '../api/client'

interface LoginPageProps {
  onLogin: () => void
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const resp = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (!resp.ok) {
        setError('Invalid password')
        return
      }
      const data = await resp.json()
      setToken(data.token)
      onLogin()
    } catch {
      setError('Connection failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-cream flex items-center justify-center font-body">
      <div className="bg-surface rounded-2xl shadow-card border border-border p-8 w-full max-w-sm">
        <h1 className="font-display font-bold text-2xl text-primary text-center mb-2">
          Planner
        </h1>
        <p className="text-secondary text-sm text-center mb-6">Sign in to your schedule</p>

        <form onSubmit={handleSubmit}>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoFocus
            className="w-full bg-cream border border-border rounded-xl px-4 py-3 text-primary placeholder-muted focus:border-accent focus:ring-1 focus:ring-accent/20 focus:outline-none mb-4"
          />
          {error && <p className="text-urgent text-sm mb-3">{error}</p>}
          <button
            type="submit"
            disabled={loading || !password}
            className="w-full py-3 bg-accent hover:bg-accent-hover rounded-xl text-white font-medium disabled:opacity-50 transition-colors"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
