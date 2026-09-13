import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Wallet } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'

export default function Navbar() {
  const { token, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const isAuthPage = ['/login', '/register'].includes(location.pathname)
  const [dark, setDark] = useState<boolean>(() => {
    const v = localStorage.getItem('theme')
    return v === 'dark'
  })

  useEffect(() => {
    const root = document.documentElement
    if (dark) {
      root.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      root.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }, [dark])

  return (
    <nav className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
      <div className="w-full px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" className="font-semibold flex items-center gap-2 hover:opacity-90">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600/10 text-blue-700 dark:bg-sky-400/15 dark:text-sky-200 ring-1 ring-blue-600/10 dark:ring-sky-300/20">
              <Wallet size={18} />
            </span>
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-700 to-violet-700 dark:from-sky-300 dark:to-fuchsia-300 font-bold tracking-tight">
              Portfolio
            </span>
          </Link>
          {!isAuthPage && token && (
            <div className="flex items-center gap-3 text-sm">
              <Link to="/" className="hover:underline dark:text-gray-100">Dashboard</Link>
              <Link to="/accounts" className="hover:underline dark:text-gray-100">Accounts</Link>
              <Link to="/transactions" className="hover:underline dark:text-gray-100">Transactions</Link>
              <Link to="/strategies" className="hover:underline dark:text-gray-100">Strategy</Link>
              <Link to="/screeners" className="hover:underline dark:text-gray-100">Screeners</Link>
              <Link to="/ipos" className="hover:underline dark:text-gray-100">IPO Tracker</Link>
              <Link to="/reports" className="hover:underline dark:text-gray-100">Reports</Link>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {!isAuthPage && (
            <button className="text-sm border dark:border-gray-700 dark:text-gray-100 px-3 py-1.5 rounded" onClick={() => setDark(d => !d)}>
              {dark ? 'Light' : 'Dark'}
            </button>
          )}
          {!isAuthPage && token && (
            <Link to="/change-password" className="text-sm border dark:border-gray-700 dark:text-gray-100 px-3 py-1.5 rounded">Change Password</Link>
          )}
          {token ? (
            <button className="text-sm bg-gray-900 text-white px-3 py-1.5 rounded" onClick={() => { logout(); navigate('/login') }}>Logout</button>
          ) : (
            !isAuthPage && <Link to="/login" className="text-sm bg-gray-900 text-white px-3 py-1.5 rounded">Login</Link>
          )}
        </div>
      </div>
    </nav>
  )
}
