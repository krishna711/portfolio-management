import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import api from '../api/client'

interface AuthContextType {
  token: string | null
  mustChangePassword: boolean
  isAdmin: boolean
  login: (email: string, password: string) => Promise<boolean>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
  refreshMe: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'))
  const [mustChangePassword, setMustChangePassword] = useState<boolean>(() => localStorage.getItem('must_change_password') === '1')
  const [isAdmin, setIsAdmin] = useState<boolean>(() => localStorage.getItem('is_admin') === '1')

  useEffect(() => {
    if (token) localStorage.setItem('token', token)
    else localStorage.removeItem('token')
  }, [token])

  const refreshMe = async () => {
    if (!token) {
      setMustChangePassword(false)
      setIsAdmin(false)
      localStorage.removeItem('must_change_password')
      localStorage.removeItem('is_admin')
      return
    }
    try {
      const res = await api.get('/auth/me')
      const must = !!res?.data?.must_change_password
      const admin = !!res?.data?.is_admin
      setMustChangePassword(must)
      setIsAdmin(admin)
      localStorage.setItem('must_change_password', must ? '1' : '0')
      localStorage.setItem('is_admin', admin ? '1' : '0')
    } catch (e: any) {
      if (e?.response?.status === 401) {
        setToken(null)
      }
    }
  }

  useEffect(() => {
    void refreshMe()
  }, [token])

  const login = async (email: string, password: string) => {
    const params = new URLSearchParams()
    params.append('username', email)
    params.append('password', password)
    const res = await api.post('/auth/login', params, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
    setToken(res.data.access_token)
    const must = !!res?.data?.must_change_password
    const admin = !!res?.data?.is_admin
    setMustChangePassword(must)
    setIsAdmin(admin)
    localStorage.setItem('must_change_password', must ? '1' : '0')
    localStorage.setItem('is_admin', admin ? '1' : '0')
    return must
  }

  const register = async (email: string, password: string) => {
    const res = await api.post('/auth/register', { email, password })
    setToken(res.data.access_token)
    const must = !!res?.data?.must_change_password
    const admin = !!res?.data?.is_admin
    setMustChangePassword(must)
    setIsAdmin(admin)
    localStorage.setItem('must_change_password', must ? '1' : '0')
    localStorage.setItem('is_admin', admin ? '1' : '0')
  }

  const logout = () => {
    setToken(null)
    setMustChangePassword(false)
    setIsAdmin(false)
    localStorage.removeItem('must_change_password')
    localStorage.removeItem('is_admin')
  }

  const value = useMemo(() => ({ token, mustChangePassword, isAdmin, login, register, logout, refreshMe }), [token, mustChangePassword, isAdmin])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
