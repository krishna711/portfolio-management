import axios, { AxiosHeaders } from 'axios'

const baseURL = (import.meta as any).env?.VITE_API_BASE || '/api'
const api = axios.create({ baseURL })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  let headers = config.headers as AxiosHeaders | undefined
  if (!headers) {
    headers = new AxiosHeaders()
  } else if (typeof (headers as any).set !== 'function') {
    headers = new AxiosHeaders(headers as any)
  }
  if (token) headers.set('Authorization', `Bearer ${token}`)
  headers.set('Accept', 'application/json')
  headers.set('Cache-Control', 'no-store')
  headers.set('Pragma', 'no-cache')
  // Add cache-busting param for GETs
  if ((config.method || 'get').toLowerCase() === 'get') {
    const ts = Date.now()
    const existing = (config.params || {}) as Record<string, any>
    config.params = { ...existing, _: ts }
  }
  config.headers = headers
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err?.response?.status
    if (status === 401) {
      try {
        localStorage.removeItem('token')
        localStorage.removeItem('must_change_password')
        localStorage.removeItem('is_admin')
      } catch {}

      const path = typeof window !== 'undefined' ? window.location.pathname : ''
      if (path !== '/login') {
        try {
          window.location.assign('/login')
        } catch {}
      }
    }
    return Promise.reject(err)
  },
)

export default api
