import { FormEvent, useEffect, useMemo, useState } from 'react'
import api from '../api/client'
import { useAuth } from '../hooks/useAuth'

const BASE_COLUMNS = [
  { key: 'name', label: 'Name' },
  { key: 'symbol', label: 'Symbol' },
  { key: 'bse_symbol', label: 'BSE' },
  { key: 'board', label: 'Type' },
  { key: 'ipo_price', label: 'IPO Price' },
  { key: 'listing_price', label: 'Listing Price' },
  { key: 'lot_size', label: 'Lot Size' },
  { key: 'listing_gain_pct', label: 'Listing Gain %' },
  { key: 'current_price', label: 'Current Price' },
  { key: 'age', label: 'Age' },
  { key: 'total_subscription', label: 'Total Sub' },
  { key: 'qib_subscription', label: 'QIB Sub' },
  { key: 'retail_subscription', label: 'Retail Sub' },
  { key: 'open_date', label: 'Open Date' },
  { key: 'closing_date', label: 'Close Date' },
  { key: 'listing_date', label: 'Listing Date' },
  { key: 'listing_on', label: 'Listing On' },
  { key: 'above_listing_price', label: 'AL' },
  { key: 'above_ipo_price', label: 'IP' },
  { key: 'st', label: 'ST' },
  { key: 'e21', label: 'E21' },
  { key: 'e50', label: 'E50' },
  { key: 'e100', label: 'E100' },
  { key: 'score', label: 'Score' },
] as const

type ColumnKey = typeof BASE_COLUMNS[number]['key'] | 'actions'

type IpoRow = {
  id: number
  name: string
  symbol: string
  bse_symbol: string | null
  color: 'none' | 'green' | 'orange' | 'yellow' | 'red' | null
  board: 'mainboard' | 'sme'
  ipo_price: number | null
  listing_price: number | null
  lot_size: number | null
  listing_gain_pct: number | null
  current_price: number | null
  st: boolean | null
  e21: boolean | null
  e50: boolean | null
  e100: boolean | null
  metrics_date: string | null
  age: string | null
  total_subscription: number | null
  qib_subscription: number | null
  retail_subscription: number | null
  open_date: string | null
  closing_date: string | null
  listing_date: string | null
  listing_on: 'nse' | 'bse' | 'both' | null
}

type IpoMetricsAlerts = {
  as_of: string | null
  st_same_5d: { symbol: string; name: string; st_up: boolean; dates: string[]; is_new?: boolean }[]
  above_ema: {
    date: string | null
    all: { symbol: string; name: string; is_new?: boolean }[]
    e21: { symbol: string; name: string }[]
    e50: { symbol: string; name: string }[]
    e100: { symbol: string; name: string }[]
  }
  score_upgrades: {
    date: string | null
    items: { symbol: string; name: string; from_score: number; to_score: number; prev_date: string; cur_date: string }[]
  }
}

function fmtNum(v: number | null | undefined, digits: number = 2) {
  if (v === null || v === undefined) return '-'
  if (typeof v !== 'number' || Number.isNaN(v)) return '-'
  return v.toFixed(digits)
}

function fmtInt(v: number | null | undefined) {
  if (v === null || v === undefined) return '-'
  if (typeof v !== 'number' || Number.isNaN(v)) return '-'
  return String(Math.round(v))
}

export default function IpoTracker() {
  const { isAdmin } = useAuth()

  const [rows, setRows] = useState<IpoRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')

  const [showCols, setShowCols] = useState(false)
  const allColumns = useMemo(() => (isAdmin ? [...BASE_COLUMNS, { key: 'actions' as const, label: 'Actions' }] : [...BASE_COLUMNS]), [isAdmin])
  const [visibleCols, setVisibleCols] = useState<Set<ColumnKey>>(() => new Set<ColumnKey>([...BASE_COLUMNS.map(c => c.key), 'actions']))

  const [editing, setEditing] = useState<IpoRow | null>(null)
  const [formOpen, setFormOpen] = useState(false)

  const [filterAgeLt1y, setFilterAgeLt1y] = useState(false)
  const [filterListingStatus, setFilterListingStatus] = useState<'listed' | 'unlisted' | 'all'>('listed')
  const [filterYear, setFilterYear] = useState<number | null>(null)
  const [filterGainMin, setFilterGainMin] = useState('')
  const [filterGainMax, setFilterGainMax] = useState('')
  const [filterAbove, setFilterAbove] = useState<'any' | 'listing' | 'ipo'>('any')
  const [filterQibMin, setFilterQibMin] = useState('')
  const [filterQibMax, setFilterQibMax] = useState('')
  const [filterScoreMin, setFilterScoreMin] = useState('')
  const [filterScoreMax, setFilterScoreMax] = useState('')
  const [filterColor, setFilterColor] = useState<'any' | 'none' | 'green' | 'orange' | 'yellow' | 'red'>('any')
  const [filterSupertrendUp, setFilterSupertrendUp] = useState(false)
  const [filterAboveEma21, setFilterAboveEma21] = useState(false)
  const [filterAboveEma50, setFilterAboveEma50] = useState(false)
  const [filterAboveEma100, setFilterAboveEma100] = useState(false)

  const [priceUpdating, setPriceUpdating] = useState(false)
  const [metricsRunning, setMetricsRunning] = useState(false)

  const [alerts, setAlerts] = useState<IpoMetricsAlerts | null>(null)
  const [alertsLoading, setAlertsLoading] = useState(false)
  const [alertsError, setAlertsError] = useState('')

  const [name, setName] = useState('')
  const [symbol, setSymbol] = useState('')
  const [bseSymbol, setBseSymbol] = useState('')
  const [board, setBoard] = useState<'mainboard' | 'sme'>('mainboard')
  const [ipoPrice, setIpoPrice] = useState<string>('')
  const [listingPrice, setListingPrice] = useState<string>('')
  const [lotSize, setLotSize] = useState<string>('')
  const [totalSub, setTotalSub] = useState<string>('')
  const [qibSub, setQibSub] = useState<string>('')
  const [retailSub, setRetailSub] = useState<string>('')
  const [openDate, setOpenDate] = useState<string>('')
  const [closingDate, setClosingDate] = useState<string>('')
  const [listingDate, setListingDate] = useState<string>('')
  const [listingOn, setListingOn] = useState<'nse' | 'bse' | 'both' | ''>('')

  const effectiveCols = useMemo(() => allColumns.filter(c => visibleCols.has(c.key)), [allColumns, visibleCols])
  const showActions = isAdmin && visibleCols.has('actions')

  const rowBySymbol = useMemo(() => {
    const m = new Map<string, IpoRow>()
    for (const r of rows) {
      const sym = (r.symbol || '').trim().toUpperCase()
      if (sym) m.set(sym, r)
    }
    return m
  }, [rows])

  const scoreForSymbol = (sym: string) => {
    const r = rowBySymbol.get((sym || '').trim().toUpperCase())
    return r ? scoreFor(r).score : null
  }

  const loadPrefs = async () => {
    try {
      const res = await api.get('/prefs/ipo_tracker_columns')
      const v = res?.data?.value
      if (Array.isArray(v)) {
        const next = new Set<ColumnKey>()
        for (const x of v) {
          if (x === 'actions') next.add('actions')
          else if (BASE_COLUMNS.some(c => c.key === x)) next.add(x as ColumnKey)
        }
        // Backfill new columns for existing users (so they show up without needing a manual reset)
        if (!next.has('above_ipo_price')) next.add('above_ipo_price')
        if (!next.has('bse_symbol')) next.add('bse_symbol')
        if (next.size) {
          setVisibleCols(next)
          void savePrefs(Array.from(next))
        }
      }
    } catch (e: any) {
      if (e?.response?.status === 404) return
      console.error('Failed to load prefs', e)
    }
  }

  const savePrefs = async (keys: ColumnKey[]) => {
    try {
      await api.put('/prefs/ipo_tracker_columns', { value: keys })
    } catch (e) {
      console.error('Failed to save prefs', e)
    }
  }

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.get('/ipos/', { params: { include_prices: 1 } })
      setRows(Array.isArray(res.data) ? res.data : [])
    } catch (e: any) {
      console.error('Failed to load IPOs', e)
      setRows([])
      setError('Failed to load IPOs')
    } finally {
      setLoading(false)
    }
  }

  const loadAlerts = async () => {
    if (!isAdmin) return
    setAlertsLoading(true)
    setAlertsError('')
    try {
      const res = await api.get('/ipos/metrics/alerts')
      setAlerts(res?.data || null)
    } catch (e: any) {
      console.error('Failed to load IPO metrics alerts', e)
      setAlerts(null)
      setAlertsError('Failed to load metrics alerts')
    } finally {
      setAlertsLoading(false)
    }
  }

  const runMetricsNow = async () => {
    if (!isAdmin) return
    setMetricsRunning(true)
    setError('')
    try {
      await api.post('/ipos/metrics/run')
      await loadAlerts()
      await load()
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Failed to run metrics'
      setError(String(msg))
    } finally {
      setMetricsRunning(false)
    }
  }

  const updatePrices = async (symbols: string[]) => {
    const syms = Array.from(new Set((symbols || []).map(s => (s || '').trim().toUpperCase()).filter(Boolean))).slice(0, 120)
    if (!syms.length) return
    setPriceUpdating(true)
    setError('')
    try {
      const res = await api.post('/ipos/prices/update', { symbols: syms })
      const prices = res?.data?.prices || {}
      setRows(prev => prev.map(r => {
        const p = prices[(r.symbol || '').trim().toUpperCase()]
        if (p === undefined) return r
        return { ...r, current_price: Number(p) }
      }))
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Failed to update prices'
      setError(String(msg))
    } finally {
      setPriceUpdating(false)
    }
  }

  useEffect(() => { void loadPrefs(); void load() }, [])
  useEffect(() => { if (isAdmin) void loadAlerts() }, [isAdmin])

  const yearOptions = useMemo(() => {
    const cur = new Date().getFullYear()
    return Array.from({ length: 5 }, (_, i) => cur - i)
  }, [])


  const onToggleCol = async (k: ColumnKey) => {
    setVisibleCols(prev => {
      const next = new Set(prev)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      void savePrefs(Array.from(next))
      return next
    })
  }

  const onStartEdit = (r: IpoRow) => {
    setFormOpen(true)
    setEditing(r)
    setName(r.name || '')
    setSymbol(r.symbol || '')
    setBseSymbol(r.bse_symbol || '')
    setBoard(r.board || 'mainboard')
    setIpoPrice(r.ipo_price === null ? '' : String(r.ipo_price))
    setListingPrice(r.listing_price === null ? '' : String(r.listing_price))
    setLotSize(r.lot_size === null ? '' : String(r.lot_size))
    setTotalSub(r.total_subscription === null ? '' : String(r.total_subscription))
    setQibSub(r.qib_subscription === null ? '' : String(r.qib_subscription))
    setRetailSub(r.retail_subscription === null ? '' : String(r.retail_subscription))
    setOpenDate(r.open_date || '')
    setClosingDate(r.closing_date || '')
    setListingDate(r.listing_date || '')
    setListingOn((r.listing_on as any) || '')
  }

  const onCancelEdit = () => {
    setEditing(null)
    setFormOpen(false)
    setName('')
    setSymbol('')
    setBseSymbol('')
    setBoard('mainboard')
    setIpoPrice('')
    setListingPrice('')
    setLotSize('')
    setTotalSub('')
    setQibSub('')
    setRetailSub('')
    setOpenDate('')
    setClosingDate('')
    setListingDate('')
    setListingOn('')
  }

  const parseNum = (s: string) => {
    const t = (s || '').trim()
    if (!t) return null
    const n = Number(t)
    return Number.isFinite(n) ? n : null
  }

  const parseIntOrNull = (s: string) => {
    const t = (s || '').trim()
    if (!t) return null
    const n = Number(t)
    if (!Number.isFinite(n)) return null
    return Math.round(n)
  }

  const payload = () => ({
    name: (name || '').trim(),
    symbol: (symbol || '').trim().toUpperCase(),
    bse_symbol: (bseSymbol || '').trim() || null,
    board,
    ipo_price: parseNum(ipoPrice),
    listing_price: parseNum(listingPrice),
    lot_size: parseIntOrNull(lotSize),
    total_subscription: parseNum(totalSub),
    qib_subscription: parseNum(qibSub),
    retail_subscription: parseNum(retailSub),
    open_date: openDate || null,
    closing_date: closingDate || null,
    listing_date: listingDate || null,
    listing_on: listingOn || null,
  })

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!isAdmin) return

    try {
      if (editing) {
        await api.patch(`/ipos/${editing.id}`, payload())
      } else {
        await api.post('/ipos/', payload())
      }
      onCancelEdit()
      await load()
    } catch (e: any) {
      console.error('Failed to save IPO', e)
      const msg = e?.response?.data?.detail || 'Failed to save IPO'
      setError(String(msg))
    }
  }

  const onDelete = async (id: number) => {
    if (!isAdmin) return
    const ok = window.confirm('Delete IPO?')
    if (!ok) return
    try {
      await api.delete(`/ipos/${id}`)
      if (editing?.id === id) onCancelEdit()
      await load()
    } catch (e) {
      console.error('Failed to delete IPO', e)
      setError('Failed to delete IPO')
    }
  }

  const filteredRows = useMemo(() => {
    const gainMin = parseNum(filterGainMin)
    const gainMax = parseNum(filterGainMax)
    const qibMin = parseNum(filterQibMin)
    const qibMax = parseNum(filterQibMax)
    const scoreMin = parseInt((filterScoreMin || '').trim() || '', 10)
    const scoreMax = parseInt((filterScoreMax || '').trim() || '', 10)
    const hasScoreMin = Number.isFinite(scoreMin)
    const hasScoreMax = Number.isFinite(scoreMax)

    const ageMonths = (d: string | null) => {
      if (!d) return null
      const dt = new Date(d)
      if (Number.isNaN(dt.getTime())) return null
      const now = new Date()
      let months = (now.getFullYear() - dt.getFullYear()) * 12 + (now.getMonth() - dt.getMonth())
      if (now.getDate() < dt.getDate()) months -= 1
      return months
    }

    const listingYear = (d: string | null) => {
      if (!d) return null
      const dt = new Date(d)
      if (Number.isNaN(dt.getTime())) return null
      return dt.getFullYear()
    }

    const todayLocal = (() => {
      const d = new Date()
      const y = d.getFullYear()
      const m = String(d.getMonth() + 1).padStart(2, '0')
      const dd = String(d.getDate()).padStart(2, '0')
      return `${y}-${m}-${dd}`
    })()

    const isListed = (r: IpoRow) => {
      const ld = r.listing_date
      if (!ld) return false
      // listing_date is YYYY-MM-DD
      return ld <= todayLocal
    }

    return rows.filter(r => {
      if (filterListingStatus === 'listed' && !isListed(r)) return false
      if (filterListingStatus === 'unlisted' && isListed(r)) return false

      const c = (r.color || 'none') as any
      if (filterColor !== 'any') {
        if (filterColor === 'none') {
          if (c !== 'none') return false
        } else {
          if (c !== filterColor) return false
        }
      }
      if (filterAgeLt1y) {
        const m = ageMonths(r.listing_date)
        if (m === null) return false
        if (m >= 12) return false
      }

      if (filterYear !== null) {
        const y = listingYear(r.listing_date)
        if (y === null) return false
        if (y !== filterYear) return false
      }

      if (gainMin !== null) {
        if (r.listing_gain_pct === null) return false
        if (r.listing_gain_pct < gainMin) return false
      }

      if (gainMax !== null) {
        if (r.listing_gain_pct === null) return false
        if (r.listing_gain_pct > gainMax) return false
      }

      if (filterAbove === 'listing') {
        if (r.current_price === null || r.listing_price === null) return false
        if (!(r.current_price >= r.listing_price)) return false
      }

      if (filterAbove === 'ipo') {
        if (r.current_price === null || r.ipo_price === null) return false
        if (!(r.current_price >= r.ipo_price)) return false
      }

      if (qibMin !== null) {
        if (r.qib_subscription === null) return false
        if (r.qib_subscription < qibMin) return false
      }

      if (qibMax !== null) {
        if (r.qib_subscription === null) return false
        if (r.qib_subscription > qibMax) return false
      }

      if (filterSupertrendUp && r.st !== true) return false
      if (filterAboveEma21 && r.e21 !== true) return false
      if (filterAboveEma50 && r.e50 !== true) return false
      if (filterAboveEma100 && r.e100 !== true) return false

      if (hasScoreMin || hasScoreMax) {
        const sc = scoreFor(r).score
        if (hasScoreMin && sc < scoreMin) return false
        if (hasScoreMax && sc > scoreMax) return false
      }

      return true
    })
  }, [rows, filterAgeLt1y, filterListingStatus, filterYear, filterGainMin, filterGainMax, filterAbove, filterQibMin, filterQibMax, filterSupertrendUp, filterAboveEma21, filterAboveEma50, filterAboveEma100, filterScoreMin, filterScoreMax, filterColor])

  const clearFilters = () => {
    setFilterAgeLt1y(false)
    setFilterListingStatus('listed')
    setFilterYear(null)
    setFilterGainMin('')
    setFilterGainMax('')
    setFilterAbove('any')
    setFilterQibMin('')
    setFilterQibMax('')
    setFilterScoreMin('')
    setFilterScoreMax('')
    setFilterColor('any')
    setFilterSupertrendUp(false)
    setFilterAboveEma21(false)
    setFilterAboveEma50(false)
    setFilterAboveEma100(false)
  }

  const onAddNew = () => {
    setFormOpen(v => !v)
    setEditing(null)
    if (!formOpen) {
      setName('')
      setSymbol('')
      setBseSymbol('')
      setBoard('mainboard')
      setIpoPrice('')
      setListingPrice('')
      setLotSize('')
      setTotalSub('')
      setQibSub('')
      setRetailSub('')
      setOpenDate('')
      setClosingDate('')
      setListingDate('')
      setListingOn('')
    }
  }

  const dot = (v: boolean | null | undefined) => {
    if (v === true) return <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 dark:bg-emerald-400" />
    if (v === false) return <span className="inline-block h-2 w-2 rounded-full bg-gray-400 dark:bg-gray-600" />
    return <span className="inline-block h-2 w-2 rounded-full bg-gray-300 dark:bg-gray-700" />
  }

  function scoreFor(r: IpoRow) {
    const st = r.st === true
    const e21 = r.e21 === true
    const e50 = r.e50 === true
    const e100 = r.e100 === true

    const close = r.current_price
    const aboveListing = close !== null && r.listing_price !== null ? close >= r.listing_price : false
    const aboveIpo = close !== null && r.ipo_price !== null ? close >= r.ipo_price : false

    const score = (st ? 1 : 0) + (e21 ? 1 : 0) + (e50 ? 1 : 0) + (e100 ? 1 : 0) + (aboveListing ? 1 : 0) + (aboveIpo ? 1 : 0)

    let cls = 'text-red-600 dark:text-red-400'
    if (score >= 5) cls = 'text-green-600 dark:text-green-400'
    else if (score >= 3) cls = 'text-orange-600 dark:text-orange-400'

    return { score, cls }
  }

  const setRowColor = async (ipoId: number, color: 'none' | 'green' | 'orange' | 'yellow' | 'red') => {
    setRows(prev => prev.map(r => (r.id === ipoId ? { ...r, color } : r)))
    try {
      await api.put(`/ipos/${ipoId}/color`, { color })
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || 'Failed to set color'))
      await load()
    }
  }

  const rowBgClass = (color: any) => {
    switch (color) {
      case 'green':
        return 'bg-green-50 dark:bg-emerald-500/10'
      case 'orange':
        return 'bg-orange-50 dark:bg-orange-500/10'
      case 'yellow':
        return 'bg-yellow-50 dark:bg-yellow-500/10'
      case 'red':
        return 'bg-red-50 dark:bg-red-500/10'
      default:
        return ''
    }
  }

  const renderCell = (r: IpoRow, k: ColumnKey) => {
    if (k === 'name') {
      const c = (r.color || 'none') as any
      return (
        <div className="flex items-center gap-2">
          <select
            className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1 text-xs dark:text-gray-100 w-12"
            style={{
              color: c === 'green' ? '#10b981' : c === 'orange' ? '#f97316' : c === 'yellow' ? '#eab308' : c === 'red' ? '#ef4444' : undefined,
            }}
            value={c}
            onChange={(e) => void setRowColor(r.id, e.target.value as any)}
            title={c}
          >
            <option value="none">-</option>
            <option value="green" style={{ color: '#10b981' }}>●</option>
            <option value="orange" style={{ color: '#f97316' }}>●</option>
            <option value="yellow" style={{ color: '#eab308' }}>●</option>
            <option value="red" style={{ color: '#ef4444' }}>●</option>
          </select>
          <span>{r.name}</span>
        </div>
      )
    }

    if (k === 'ipo_price') return fmtNum(r.ipo_price)
    if (k === 'listing_price') return fmtNum(r.listing_price)
    if (k === 'lot_size') return fmtInt(r.lot_size)
    if (k === 'listing_gain_pct') return r.listing_gain_pct === null ? '-' : `${fmtNum(r.listing_gain_pct)}%`
    if (k === 'current_price') return fmtNum(r.current_price)
    if (k === 'above_listing_price') return dot(r.current_price !== null && r.listing_price !== null ? (r.current_price >= r.listing_price) : null)
    if (k === 'above_ipo_price') return dot(r.current_price !== null && r.ipo_price !== null ? (r.current_price >= r.ipo_price) : null)

    if (k === 'st') return dot(r.st)
    if (k === 'e21') return dot(r.e21)
    if (k === 'e50') return dot(r.e50)
    if (k === 'e100') return dot(r.e100)
    if (k === 'score') {
      const { score, cls } = scoreFor(r)
      return <span className={cls}>{score}</span>
    }

    if (k === 'board') return r.board === 'sme' ? 'SME' : 'Mainboard'
    if (k === 'listing_on') {
      if (!r.listing_on) return '-'
      if (r.listing_on === 'both') return 'NSE+BSE'
      return r.listing_on.toUpperCase()
    }
    const v = (r as any)[k]
    return v ?? '-'
  }

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <div className="text-lg font-semibold">IPO Tracker</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Past and upcoming IPOs (latest to past)</div>
          </div>
          <div className="flex items-center gap-2">
            {isAdmin && (
              <button
                className="text-sm bg-gray-900 text-white px-3 py-1.5 rounded"
                onClick={() => {
                  if (formOpen) onCancelEdit()
                  else onAddNew()
                }}
              >
                {formOpen ? 'Close Form' : 'Add IPO'}
              </button>
            )}
            <button className="text-sm border dark:border-gray-700 dark:text-gray-100 px-3 py-1.5 rounded" onClick={() => setShowCols(v => !v)}>
              Columns
            </button>
            {isAdmin && (
              <button
                className="text-sm border dark:border-gray-700 dark:text-gray-100 px-3 py-1.5 rounded"
                disabled={metricsRunning}
                onClick={() => void runMetricsNow()}
              >
                {metricsRunning ? 'Running...' : 'Run Metrics Now'}
              </button>
            )}
            <button
              className="text-sm border dark:border-gray-700 dark:text-gray-100 px-3 py-1.5 rounded"
              disabled={priceUpdating}
              onClick={() => void updatePrices(filteredRows.map(r => r.symbol))}
            >
              {priceUpdating ? 'Updating...' : 'Update Prices'}
            </button>
            <button
              className="text-sm border dark:border-gray-700 dark:text-gray-100 px-3 py-1.5 rounded"
              onClick={() => {
                void load()
                if (isAdmin) void loadAlerts()
              }}
            >
              Refresh
            </button>
          </div>
        </div>

        {showCols && (
          <div className="mt-4 border dark:border-gray-700 rounded p-3">
            <div className="text-sm text-gray-600 dark:text-gray-400 mb-2">Show/Hide Columns (saved per user)</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {allColumns.map(c => (
                <label key={c.key} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={visibleCols.has(c.key)} onChange={() => void onToggleCol(c.key)} />
                  <span>{c.label}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        {isAdmin && (
          <div className="mt-4">
            <div className="text-sm font-semibold mb-2 dark:text-gray-100">Metrics Alerts</div>
            <div className="grid grid-cols-1 gap-3 items-start">
              <div className="border dark:border-gray-700 rounded p-3 bg-gray-50 dark:bg-gray-900/40">
                <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">ST same (last 5 days) · {alerts?.st_same_5d?.length || 0} matches</div>
                {alertsLoading ? (
                  <div className="text-sm text-gray-600 dark:text-gray-400">Loading...</div>
                ) : (
                  <div className="space-y-1">
                    <div className="pr-1">
                      {(() => {
                        const upSyms = (alerts?.st_same_5d || [])
                          .filter(x => x.st_up)
                          .slice(0, 120)
                          .map(x => String(x.symbol || '').trim().toUpperCase())
                          .filter(Boolean)
                        if (!upSyms.length) return <div className="text-sm text-gray-600 dark:text-gray-400">None</div>

                        const emaSet = new Set(
                          (alerts?.above_ema?.all || [])
                            .map(x => String(x.symbol || '').trim().toUpperCase())
                            .filter(Boolean)
                        )

                        const newSet = new Set(
                          (alerts?.st_same_5d || [])
                            .filter(x => x.st_up && x.is_new)
                            .map(x => String(x.symbol || '').trim().toUpperCase())
                            .filter(Boolean)
                        )

                        const sorted = [...upSyms].sort((a, b) => {
                          const sa = scoreForSymbol(a)
                          const sb = scoreForSymbol(b)
                          const da = sa === null ? -1 : sa
                          const db = sb === null ? -1 : sb
                          if (db !== da) return db - da
                          return a.localeCompare(b)
                        })

                        return (
                          <div className="text-xs font-mono whitespace-normal break-words text-emerald-700 dark:text-emerald-300">
                            {sorted.map((sym, i) => {
                              const sc = scoreForSymbol(sym)
                              const base = sc === null ? sym : `${sym}(${sc})`
                              const txt = emaSet.has(sym) ? `${base}✓` : base
                              const isNew = newSet.has(sym)
                              return (
                                <span key={sym} className={isNew ? 'bg-yellow-200/50 dark:bg-yellow-400/20 rounded px-0.5' : ''}>
                                  {i ? ', ' : ''}{txt}
                                </span>
                              )
                            })}
                          </div>
                        )
                      })()}
                    </div>
                  </div>
                )}
              </div>

              <div className="border dark:border-gray-700 rounded p-3 bg-gray-50 dark:bg-gray-900/40">
                <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">Close above EMAs (All 3) · All 3: {alerts?.above_ema?.all?.length || 0} | E21: {alerts?.above_ema?.e21?.length || 0} | E50: {alerts?.above_ema?.e50?.length || 0} | E100: {alerts?.above_ema?.e100?.length || 0}</div>
                {alertsLoading ? (
                  <div className="text-sm text-gray-600 dark:text-gray-400">Loading...</div>
                ) : (
                  <div className="space-y-1">
                    <div className="pr-1">
                      {!!alerts?.above_ema?.all?.length ? (
                        <div className="text-xs font-mono whitespace-normal break-words text-gray-900 dark:text-gray-100">
                          {(() => {
                            const stSet = new Set(
                              (alerts?.st_same_5d || [])
                                .filter(x => x.st_up)
                                .map(x => String(x.symbol || '').trim().toUpperCase())
                                .filter(Boolean)
                            )

                            const newSet = new Set(
                              (alerts?.above_ema?.all || [])
                                .filter(x => x.is_new)
                                .map(x => String(x.symbol || '').trim().toUpperCase())
                                .filter(Boolean)
                            )

                            const syms = (alerts?.above_ema?.all || [])
                              .slice(0, 200)
                              .map(x => String(x.symbol || '').trim().toUpperCase())
                              .filter(Boolean)

                            const sorted = syms.sort((a, b) => {
                              const sa = scoreForSymbol(a)
                              const sb = scoreForSymbol(b)
                              const da = sa === null ? -1 : sa
                              const db = sb === null ? -1 : sb
                              if (db !== da) return db - da
                              return a.localeCompare(b)
                            })

                            return (
                              <>
                                {sorted.map((sym, i) => {
                                  const sc = scoreForSymbol(sym)
                                  const base = sc === null ? sym : `${sym}(${sc})`
                                  const txt = stSet.has(sym) ? `${base}✓` : base
                                  const isNew = newSet.has(sym)
                                  return (
                                    <span key={sym} className={isNew ? 'bg-yellow-200/50 dark:bg-yellow-400/20 rounded px-0.5' : ''}>
                                      {i ? ', ' : ''}{txt}
                                    </span>
                                  )
                                })}
                              </>
                            )
                          })()}
                        </div>
                      ) : (
                        <div className="text-sm text-gray-600 dark:text-gray-400">None</div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div className="border dark:border-gray-700 rounded p-3 bg-gray-50 dark:bg-gray-900/40">
                <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">Score upgrades · {alerts?.score_upgrades?.items?.length || 0}</div>
                {alertsLoading ? (
                  <div className="text-sm text-gray-600 dark:text-gray-400">Loading...</div>
                ) : (
                  <div className="space-y-1">
                    <div className="pr-1">
                      {!!alerts?.score_upgrades?.items?.length ? (
                        <div className="text-xs font-mono whitespace-normal break-words text-gray-900 dark:text-gray-100">
                          {(alerts?.score_upgrades?.items || [])
                            .slice(0, 120)
                            .map(x => {
                              const sym = String(x.symbol || '').trim().toUpperCase()
                              const sc = scoreForSymbol(sym)
                              const head = sc === null ? sym : `${sym}(${sc})`
                              return { sym, sc, head, txt: `${head} ${x.from_score}→${x.to_score}` }
                            })
                            .sort((a, b) => {
                              const da = a.sc === null ? -1 : a.sc
                              const db = b.sc === null ? -1 : b.sc
                              if (db !== da) return db - da
                              return a.sym.localeCompare(b.sym)
                            })
                            .map(x => x.txt)
                            .join(', ')}
                        </div>
                      ) : (
                        <div className="text-sm text-gray-600 dark:text-gray-400">None</div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {alertsError && <div className="mt-2 text-sm text-red-600 dark:text-red-400">{alertsError}</div>}
          </div>
        )}

        {error && <div className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</div>}
        {loading && <div className="mt-3 text-sm text-gray-600 dark:text-gray-400">Loading...</div>}
      </div>

      {isAdmin && formOpen && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="font-semibold">{editing ? 'Edit IPO' : 'Add IPO'}</div>
            <button className="text-sm border dark:border-gray-700 dark:text-gray-100 px-3 py-1.5 rounded" type="button" onClick={onCancelEdit}>
              Close
            </button>
          </div>
          <form onSubmit={onSubmit} className="grid grid-cols-1 md:grid-cols-6 gap-3">
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 md:col-span-2" placeholder="Name" value={name} onChange={e => setName(e.target.value)} required />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Symbol" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} required />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="BSE Code" value={bseSymbol} onChange={e => setBseSymbol(e.target.value)} />
            <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" value={board} onChange={e => setBoard(e.target.value as any)}>
              <option value="mainboard">Mainboard</option>
              <option value="sme">SME</option>
            </select>
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="IPO Price" type="number" step="0.01" value={ipoPrice} onChange={e => setIpoPrice(e.target.value)} />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Listing Price" type="number" step="0.01" value={listingPrice} onChange={e => setListingPrice(e.target.value)} />

            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Lot Size" type="number" step="1" value={lotSize} onChange={e => setLotSize(e.target.value)} />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Total Sub" type="number" step="0.01" value={totalSub} onChange={e => setTotalSub(e.target.value)} />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="QIB Sub" type="number" step="0.01" value={qibSub} onChange={e => setQibSub(e.target.value)} />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Retail Sub" type="number" step="0.01" value={retailSub} onChange={e => setRetailSub(e.target.value)} />

            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" type="date" value={openDate} onChange={e => setOpenDate(e.target.value)} />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" type="date" value={closingDate} onChange={e => setClosingDate(e.target.value)} />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" type="date" value={listingDate} onChange={e => setListingDate(e.target.value)} />

            <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" value={listingOn} onChange={e => setListingOn(e.target.value as any)}>
              <option value="">Listing On</option>
              <option value="nse">NSE</option>
              <option value="bse">BSE</option>
              <option value="both">Both</option>
            </select>

            <div className="md:col-span-6 flex gap-2">
              <button className="bg-gray-900 text-white px-4 py-2 rounded" type="submit">{editing ? 'Save' : 'Create'}</button>
              {editing && (
                <button className="px-4 py-2 border dark:border-gray-700 rounded" type="button" onClick={onCancelEdit}>Cancel</button>
              )}
            </div>
          </form>
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 mb-3">
          <div className="font-semibold">IPOs</div>
          <div className="text-sm text-gray-600 dark:text-gray-400">
            Showing {filteredRows.length} / {rows.length}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-6 gap-3 mb-4">
          <label className="flex items-center gap-2 text-sm md:col-span-2">
            <input type="checkbox" checked={filterAgeLt1y} onChange={e => setFilterAgeLt1y(e.target.checked)} />
            <span>Age &lt; 1 year</span>
          </label>

          <div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">Status</div>
            <select
              className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 text-sm"
              value={filterListingStatus}
              onChange={(e) => setFilterListingStatus(e.target.value as any)}
            >
              <option value="listed">Listed</option>
              <option value="unlisted">Unlisted</option>
              <option value="all">All</option>
            </select>
          </div>

          <div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">Year (listing)</div>
            <select
              className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 text-sm"
              value={filterYear === null ? '' : String(filterYear)}
              onChange={(e) => {
                const v = (e.target.value || '').trim()
                setFilterYear(v ? Number(v) : null)
              }}
            >
              <option value="">Any</option>
              {yearOptions.map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>

          <div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">Listing Gain % (min)</div>
            <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 text-sm" type="number" step="0.01" value={filterGainMin} onChange={e => setFilterGainMin(e.target.value)} />
          </div>
          <div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">Listing Gain % (max)</div>
            <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 text-sm" type="number" step="0.01" value={filterGainMax} onChange={e => setFilterGainMax(e.target.value)} />
          </div>

          <div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">Above</div>
            <select className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 text-sm" value={filterAbove} onChange={e => setFilterAbove(e.target.value as any)}>
              <option value="any">Any</option>
              <option value="listing">Above listing price</option>
              <option value="ipo">Above IPO price</option>
            </select>
          </div>

          <div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">Color</div>
            <select className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 text-sm" value={filterColor} onChange={e => setFilterColor(e.target.value as any)}>
              <option value="any">Any</option>
              <option value="none">None</option>
              <option value="green">Green</option>
              <option value="orange">Orange</option>
              <option value="yellow">Yellow</option>
              <option value="red">Red</option>
            </select>
          </div>

          <div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">QIB Sub (min)</div>
            <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 text-sm" type="number" step="0.01" value={filterQibMin} onChange={e => setFilterQibMin(e.target.value)} />
          </div>
          <div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">QIB Sub (max)</div>
            <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 text-sm" type="number" step="0.01" value={filterQibMax} onChange={e => setFilterQibMax(e.target.value)} />
          </div>

          <div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">Score (min)</div>
            <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 text-sm" type="number" min={0} max={6} step={1} value={filterScoreMin} onChange={e => setFilterScoreMin(e.target.value)} />
          </div>
          <div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">Score (max)</div>
            <input className="w-full border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 text-sm" type="number" min={0} max={6} step={1} value={filterScoreMax} onChange={e => setFilterScoreMax(e.target.value)} />
          </div>

          <label className="flex items-center gap-2 text-sm md:col-span-2">
            <input type="checkbox" checked={filterSupertrendUp} onChange={e => setFilterSupertrendUp(e.target.checked)} />
            <span>Supertrend (8,3.2) Positive</span>
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={filterAboveEma21} onChange={e => setFilterAboveEma21(e.target.checked)} />
            <span>Above EMA 21</span>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={filterAboveEma50} onChange={e => setFilterAboveEma50(e.target.checked)} />
            <span>Above EMA 50</span>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={filterAboveEma100} onChange={e => setFilterAboveEma100(e.target.checked)} />
            <span>Above EMA 100</span>
          </label>

          <div className="md:col-span-6">
            <button className="text-sm border dark:border-gray-700 dark:text-gray-100 px-3 py-1.5 rounded" type="button" onClick={clearFilters}>
              Clear Filters
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b dark:border-gray-700">
                {effectiveCols.map(c => (
                  <th key={c.key} className="py-2">{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredRows.map(r => (
                <tr key={r.id} className={`border-b dark:border-gray-700 last:border-b-0 ${rowBgClass(r.color)}`}>
                  {effectiveCols.map(c => (
                    <td key={c.key} className="py-2">
                      {c.key === 'actions' ? (
                        showActions ? (
                          <div className="flex gap-2">
                            <button className="px-3 py-1 border dark:border-gray-700 rounded" onClick={() => onStartEdit(r)}>Edit</button>
                            <button className="px-3 py-1 border dark:border-gray-700 rounded text-red-600" onClick={() => void onDelete(r.id)}>Delete</button>
                          </div>
                        ) : null
                      ) : (
                        renderCell(r, c.key)
                      )}
                    </td>
                  ))}
                </tr>
              ))}
              {!filteredRows.length && !loading && (
                <tr>
                  <td className="py-6 text-gray-600 dark:text-gray-400" colSpan={effectiveCols.length}>
                    No IPOs
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
