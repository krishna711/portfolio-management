import { FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function Register() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { register } = useAuth()
  const nav = useNavigate()

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      setLoading(true)
      await register(email, password)
      nav('/')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto mt-16 bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
      <h1 className="text-xl font-semibold">Register</h1>
      <form onSubmit={onSubmit} className="mt-4 space-y-3">
        <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} required />
        <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} required />
        {error && <div className="text-sm text-red-600">{error}</div>}
        <button disabled={loading} className="w-full bg-gray-900 text-white rounded py-2">{loading ? 'Creating...' : 'Register'}</button>
      </form>
      <div className="text-sm mt-3 text-gray-600 dark:text-gray-400">Have an account? <Link to="/login" className="underline">Login</Link></div>
    </div>
  )
}
