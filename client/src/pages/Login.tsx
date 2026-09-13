import { FormEvent, useState } from 'react'
import { useLocation, useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { login } = useAuth()
  const nav = useNavigate()
  const loc = useLocation() as any

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      setLoading(true)
      const must = await login(email, password)
      if (must) {
        nav('/change-password')
      } else {
        const to = loc.state?.from?.pathname || '/'
        nav(to)
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto mt-16 bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
      <h1 className="text-xl font-semibold">Login</h1>
      <form onSubmit={onSubmit} className="mt-4 space-y-3">
        <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} required />
        <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} required />
        {error && <div className="text-sm text-red-600">{error}</div>}
        <button disabled={loading} className="w-full bg-gray-900 text-white rounded py-2">{loading ? 'Signing in...' : 'Login'}</button>
      </form>
      <div className="text-sm mt-3 text-gray-600 dark:text-gray-400">No account? <Link to="/register" className="underline">Register</Link></div>
      <div className="text-sm mt-2 text-gray-600 dark:text-gray-400"><Link to="/forgot-password" className="underline">Forgot password?</Link></div>
    </div>
  )
}
