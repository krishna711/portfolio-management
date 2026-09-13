import { FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/client'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSent(false)
    try {
      setLoading(true)
      await api.post('/auth/reset_password', { email })
      setSent(true)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to reset password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto mt-16 bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
      <h1 className="text-xl font-semibold">Reset Password</h1>
      <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
        Enter your email. If an account exists, a temporary password will be sent.
      </div>
      <form onSubmit={onSubmit} className="mt-4 space-y-3">
        <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} required />
        {error && <div className="text-sm text-red-600">{error}</div>}
        {sent && <div className="text-sm text-green-700">If your email exists, a temporary password has been sent.</div>}
        <button disabled={loading} className="w-full bg-gray-900 text-white rounded py-2">{loading ? 'Sending...' : 'Send Temporary Password'}</button>
      </form>
      <div className="text-sm mt-3 text-gray-600 dark:text-gray-400">
        Back to <Link to="/login" className="underline">Login</Link>
      </div>
    </div>
  )
}
