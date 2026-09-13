import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import { useAuth } from '../hooks/useAuth'

export default function ChangePassword() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const nav = useNavigate()
  const { refreshMe } = useAuth()

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(false)
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    try {
      setLoading(true)
      await api.post('/auth/change_password', { current_password: currentPassword, new_password: newPassword })
      await refreshMe()
      setSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      window.setTimeout(() => nav('/'), 600)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to change password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto mt-16 bg-white dark:bg-gray-800 p-6 rounded-lg shadow">
      <h1 className="text-xl font-semibold">Change Password</h1>
      <form onSubmit={onSubmit} className="mt-4 space-y-3">
        <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Current password" type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} required />
        <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="New password" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required />
        <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Confirm new password" type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required />
        {error && <div className="text-sm text-red-600">{error}</div>}
        {success && <div className="text-sm text-green-700">Password updated.</div>}
        <button disabled={loading} className="w-full bg-gray-900 text-white rounded py-2">{loading ? 'Saving...' : 'Save Password'}</button>
      </form>
    </div>
  )
}
