import { useEffect, useMemo, useState } from 'react'
import api from '../api/client'
import Card from '../components/Card'
import EquityChart from '../charts/EquityChart'
import LWCHoldingChart from '../charts/LWCHoldingChart'
import { StickyNote } from 'lucide-react'

function formatCurrency(n: number | null | undefined) {
  if (n == null) return '-'
  return n.toLocaleString(undefined, { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })
}

function formatPct(n: number | null | undefined) {
  if (n == null) return '-'
  return `${n.toFixed(2)}%`
}

function formatDateTime(s: string | null | undefined) {
  if (!s) return '-'
  const d = new Date(s)
  return isNaN(d.getTime()) ? String(s) : d.toLocaleString()
}

function pnClass(n: number | null | undefined) {
  if (n == null) return ''
  if (n > 0) return 'text-green-600'
  if (n < 0) return 'text-red-600'
  return ''
}

export default function Dashboard() {
  const [summary, setSummary] = useState<any>(null)
  const [curve, setCurve] = useState<any>(null)
  const [curveStatus, setCurveStatus] = useState<string>('')
  const [sectionMeta, setSectionMeta] = useState<Record<string, any>>({})
  const [acct, setAcct] = useState<{ accounts: any[] } | null>(null)
  const [holdings, setHoldings] = useState<{ holdings: any[] } | null>(null)
  const [charts, setCharts] = useState<{ charts: any[] } | null>(null)
  const [chartFor, setChartFor] = useState<{ holding_id: number; data: any } | null>(null)
  const [useHeikin, setUseHeikin] = useState<boolean>(false)
  const [showVolume, setShowVolume] = useState<boolean>(true)
  const [showRSI, setShowRSI] = useState<boolean>(true)
  const [slDraft, setSlDraft] = useState<string>('0')
  const [slSaving, setSlSaving] = useState<boolean>(false)
  const [noteModal, setNoteModal] = useState<{ symbol: string; note: string } | null>(null)

  // Filters / sorting for holdings
  const [acctFilter, setAcctFilter] = useState<string>('')
  const [symbolFilter, setSymbolFilter] = useState<string>('')
  const [mvMin, setMvMin] = useState<string>('')
  const [mvMax, setMvMax] = useState<string>('')
  const [invMin, setInvMin] = useState<string>('')
  const [invMax, setInvMax] = useState<string>('')
  const [unrMin, setUnrMin] = useState<string>('')
  const [unrMax, setUnrMax] = useState<string>('')
  const [rrMin, setRrMin] = useState<string>('')
  const [rrMax, setRrMax] = useState<string>('')
  const [dpMin, setDpMin] = useState<string>('')
  const [dpMax, setDpMax] = useState<string>('')
  const [sortKey, setSortKey] = useState<string>('market_value')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [statusFilter, setStatusFilter] = useState<string>('active')

  const maxPollAttempts = 180

  const fetchWithRetry = async <T,>(fn: () => Promise<T>, tries: number, delayMs: number): Promise<T> => {
    let lastErr: any
    for (let i = 0; i < tries; i++) {
      try {
        return await fn()
      } catch (e) {
        lastErr = e
        if (i < tries - 1) {
          const ms = Math.min(delayMs * Math.pow(2, i), 8000)
          await new Promise((r) => setTimeout(r, ms))
        }
      }
    }
    throw lastErr
  }

  const schedulePoll = (
    timers: number[],
    fn: () => void,
    ms: number,
  ) => {
    const id = window.setTimeout(fn, ms)
    timers.push(id)
  }

  useEffect(() => {
    let cancelled = false
    const timers: number[] = []

    const shouldPoll = (data: any) => {
      const st = data?._meta?.status
      return st === 'warming' || st === 'stale'
    }

    const loadSummary = async (attempt = 0) => {
      try {
        const res: any = await fetchWithRetry(() => api.get('/dashboard/summary'), 2, 400)
        if (cancelled) return
        setSummary(res?.data ?? null)
        setSectionMeta((m) => ({ ...m, summary: res?.data?._meta || null }))
        if (shouldPoll(res?.data) && attempt < maxPollAttempts) {
          schedulePoll(timers, () => { void loadSummary(attempt + 1) }, 1200)
        }
      } catch {
        if (cancelled) return
        if (attempt < maxPollAttempts) schedulePoll(timers, () => { void loadSummary(attempt + 1) }, 1500)
      }
    }

    const loadCurve = async (attempt = 0) => {
      try {
        const res: any = await fetchWithRetry(() => api.get('/dashboard/equity_curve?days=60'), 2, 500)
        if (cancelled) return
        const cdata = res?.data || {}
        setSectionMeta((m) => ({ ...m, equity_curve: cdata?._meta || null }))
        const dates = Array.isArray(cdata.dates) ? cdata.dates : []
        const pv = Array.isArray(cdata.portfolio_values)
          ? cdata.portfolio_values
          : (Array.isArray(cdata.values) ? cdata.values : [])
        const rv = Array.isArray(cdata.realized_values) ? cdata.realized_values : []
        const uv = Array.isArray(cdata.unrealized_values) ? cdata.unrealized_values : []
        const st = cdata?._meta?.status
        setCurveStatus(typeof st === 'string' ? st : '')

        const anyNonZero = [...pv, ...rv, ...uv].some((x: any) => Number(x) !== 0)
        if (!(st === 'warming' && !anyNonZero)) {
          setCurve({ dates, portfolio_values: pv, realized_values: rv, unrealized_values: uv })
        }
        if (shouldPoll(res?.data) && attempt < maxPollAttempts) {
          schedulePoll(timers, () => { void loadCurve(attempt + 1) }, 2500)
        }
      } catch {
        if (cancelled) return
        if (attempt < maxPollAttempts) schedulePoll(timers, () => { void loadCurve(attempt + 1) }, 3000)
      }
    }

    const loadAccountBreakdown = async (attempt = 0) => {
      try {
        const res: any = await fetchWithRetry(() => api.get('/dashboard/account_breakdown'), 2, 400)
        if (cancelled) return
        const adata = res?.data || {}
        setAcct(Array.isArray(adata.accounts) ? adata : { accounts: [] })
        setSectionMeta((m) => ({ ...m, account_breakdown: res?.data?._meta || null }))
        if (shouldPoll(res?.data) && attempt < maxPollAttempts) {
          schedulePoll(timers, () => { void loadAccountBreakdown(attempt + 1) }, 1800)
        }
      } catch {
        if (cancelled) return
        if (attempt < maxPollAttempts) schedulePoll(timers, () => { void loadAccountBreakdown(attempt + 1) }, 2000)
      }
    }

    const loadHoldings = async (attempt = 0) => {
      try {
        const res: any = await fetchWithRetry(() => api.get('/dashboard/holdings_pl'), 2, 600)
        if (cancelled) return
        const hdata = res?.data || {}
        setHoldings(Array.isArray(hdata.holdings) ? hdata : { holdings: [] })
        setSectionMeta((m) => ({ ...m, holdings_pl: res?.data?._meta || null }))
        if (shouldPoll(res?.data) && attempt < maxPollAttempts) {
          schedulePoll(timers, () => { void loadHoldings(attempt + 1) }, 1500)
        }
      } catch {
        if (cancelled) return
        if (attempt < maxPollAttempts) schedulePoll(timers, () => { void loadHoldings(attempt + 1) }, 2000)
      }
    }

    const loadActiveCharts = async (attempt = 0) => {
      try {
        const res: any = await fetchWithRetry(() => api.get('/dashboard/active_holdings_charts?days=90'), 2, 800)
        if (cancelled) return
        const predata = res?.data || {}
        setCharts(Array.isArray(predata.charts) ? predata : { charts: [] })
        setSectionMeta((m) => ({ ...m, active_holdings_charts: res?.data?._meta || null }))
        if (shouldPoll(res?.data) && attempt < maxPollAttempts) {
          schedulePoll(timers, () => { void loadActiveCharts(attempt + 1) }, 3500)
        }
      } catch {
        if (cancelled) return
        if (attempt < maxPollAttempts) schedulePoll(timers, () => { void loadActiveCharts(attempt + 1) }, 4000)
      }
    }

    void loadSummary()
    void loadCurve()
    void loadAccountBreakdown()
    void loadHoldings()
    schedulePoll(timers, () => { void loadActiveCharts() }, 1500)

    return () => {
      cancelled = true
      timers.forEach((t) => clearTimeout(t))
    }
  }, [])

  const loadHoldingChart = async (holdingId: number, days: number, attempt = 0) => {
    const url = `/dashboard/holding_chart?holding_id=${holdingId}&days=${days}`
    try {
      const res: any = await fetchWithRetry(() => api.get(url), 2, 600)
      const data = res?.data
      setChartFor({ holding_id: holdingId, data })
      setSlDraft(String(data?.sl_price || 0))
      const st = data?._meta?.status
      if ((st === 'warming' || st === 'stale') && attempt < maxPollAttempts) {
        window.setTimeout(() => { void loadHoldingChart(holdingId, days, attempt + 1) }, 1200)
      }
    } catch {
      if (attempt < maxPollAttempts) {
        window.setTimeout(() => { void loadHoldingChart(holdingId, days, attempt + 1) }, 1500)
      }
    }
  }

  const refreshHoldings = async (attempt = 0) => {
    try {
      const res: any = await fetchWithRetry(() => api.get('/dashboard/holdings_pl'), 2, 600)
      const data = res?.data || {}
      setHoldings(Array.isArray(data.holdings) ? data : { holdings: [] })
      const st = data?._meta?.status
      if ((st === 'warming' || st === 'stale') && attempt < maxPollAttempts) {
        window.setTimeout(() => { void refreshHoldings(attempt + 1) }, 1200)
      }
    } catch {
      if (attempt < maxPollAttempts) window.setTimeout(() => { void refreshHoldings(attempt + 1) }, 1500)
    }
  }

  const chartData = useMemo(() => {
    const dates: string[] = (curve && Array.isArray(curve.dates)) ? curve.dates : []
    const pv: number[] = (curve && Array.isArray(curve.portfolio_values)) ? curve.portfolio_values : []
    const rv: number[] = (curve && Array.isArray(curve.realized_values)) ? curve.realized_values : []
    const uv: number[] = (curve && Array.isArray(curve.unrealized_values)) ? curve.unrealized_values : []
    return dates
      .map((d, i) => ({
        date: d,
        portfolio_value: Number(pv[i] ?? 0),
        realized: Number(rv[i] ?? 0),
        unrealized: Number(uv[i] ?? 0),
      }))
      .filter((p) => typeof p.date === 'string' && p.date.length > 0 && Number.isFinite(p.portfolio_value))
  }, [curve])

  const dashboardLastUpdatedAt = useMemo(() => {
    const ts = Object.values(sectionMeta)
      .map((m: any) => m?.cache_updated_at)
      .filter((x: any) => typeof x === 'string')
      .map((x: string) => new Date(x).getTime())
      .filter((n: number) => Number.isFinite(n))
    if (!ts.length) return ''
    return new Date(Math.max(...ts)).toISOString()
  }, [sectionMeta])

  const anyBackendRefreshing = useMemo(() => {
    return Object.values(sectionMeta).some((m: any) => m?.status === 'warming' || m?.status === 'stale')
  }, [sectionMeta])

  const sectionStates = useMemo(() => {
    const summaryMeta = sectionMeta.summary
    const acctMeta = sectionMeta.account_breakdown
    const holdingsMeta = sectionMeta.holdings_pl
    const curveMeta = sectionMeta.equity_curve
    const activeChartsMeta = sectionMeta.active_holdings_charts

    const summaryLoaded = summary?.portfolio_value != null && summaryMeta?.status !== 'warming'
    const curveLoaded = chartData.length > 0 || (curveMeta?.status !== 'warming' && curve != null)
    const acctLoaded = acct != null && acctMeta?.status !== 'warming'
    const holdingsLoaded = holdings != null && holdingsMeta?.status !== 'warming'
    const activeChartsLoaded = charts != null && activeChartsMeta?.status !== 'warming'
    return [
      { key: 'Summary', id: 'summary', loaded: summaryLoaded, meta: summaryMeta },
      { key: 'Breakdown', id: 'account_breakdown', loaded: acctLoaded, meta: acctMeta },
      { key: 'Holdings', id: 'holdings_pl', loaded: holdingsLoaded, meta: holdingsMeta },
      { key: 'Equity Curve', id: 'equity_curve', loaded: curveLoaded, meta: curveMeta },
      { key: 'Active Charts', id: 'active_holdings_charts', loaded: activeChartsLoaded, meta: activeChartsMeta },
    ]
  }, [summary, acct, holdings, charts, chartData.length, curve, sectionMeta])

  const slBreached = useMemo(() => {
    return (holdings?.holdings || []).filter((x: any) => (x.quantity || 0) > 0 && (!!x.sl_breached || !!x.sma23_breached))
  }, [holdings])

  const targetsHit = useMemo(() => {
    return (holdings?.holdings || []).filter((x: any) => x.r1_hit || x.r2_hit || x.r3_hit)
  }, [holdings])

  const tlslHit = useMemo(() => {
    return (holdings?.holdings || []).filter((x: any) => !!x.tlsl_hit)
  }, [holdings])

  const holdingNotes = useMemo(() => {
    const by: Record<number, string> = {}
    for (const h of (holdings?.holdings || []) as any[]) {
      const n = (h?.notes || '').trim()
      if (h?.holding_id != null && n) by[Number(h.holding_id)] = n
    }
    return by
  }, [holdings])

  const accountOptions = useMemo(() => {
    return Array.from(new Set((holdings?.holdings || []).map((x: any) => x.account_name)))
  }, [holdings])

  const filteredHoldings = useMemo(() => {
    let rows = holdings?.holdings || []
    if (acctFilter) rows = rows.filter((r: any) => r.account_name === acctFilter)
    if (statusFilter === 'active') rows = rows.filter((r: any) => (r.quantity || 0) > 0)
    else if (statusFilter === 'sold') rows = rows.filter((r: any) => (r.quantity || 0) <= 0)
    if (symbolFilter) rows = rows.filter((r: any) => r.symbol?.toLowerCase().includes(symbolFilter.toLowerCase()))
    const toNum = (s: string) => (s === '' ? null : Number(s))
    const mv0 = toNum(mvMin), mv1 = toNum(mvMax)
    const iv0 = toNum(invMin), iv1 = toNum(invMax)
    const ur0 = toNum(unrMin), ur1 = toNum(unrMax)
    const rr0 = toNum(rrMin), rr1 = toNum(rrMax)
    const dp0 = toNum(dpMin), dp1 = toNum(dpMax)
    rows = rows.filter((r: any) => (
      (mv0 == null || r.market_value >= mv0) && (mv1 == null || r.market_value <= mv1) &&
      (iv0 == null || r.invested_value >= iv0) && (iv1 == null || r.invested_value <= iv1) &&
      (ur0 == null || r.unrealized_pl >= ur0) && (ur1 == null || r.unrealized_pl <= ur1) &&
      (rr0 == null || r.realized_pl >= rr0) && (rr1 == null || r.realized_pl <= rr1) &&
      (dp0 == null || r.daily_pl >= dp0) && (dp1 == null || r.daily_pl <= dp1)
    ))
    const key = sortKey as keyof any
    rows = [...rows].sort((a: any, b: any) => {
      const av = a[key]
      const bv = b[key]
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (typeof av === 'string' && typeof bv === 'string') {
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
      }
      return sortDir === 'asc' ? (av - bv) : (bv - av)
    })
    return rows
  }, [holdings, acctFilter, statusFilter, symbolFilter, mvMin, mvMax, invMin, invMax, unrMin, unrMax, rrMin, rrMax, dpMin, dpMax, sortKey, sortDir])

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow px-4 py-3 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-gray-700 dark:text-gray-300">
            {dashboardLastUpdatedAt ? (
              <>
                Showing cached copy. Last updated at: {formatDateTime(dashboardLastUpdatedAt)}
                {anyBackendRefreshing ? ' (Refreshing in background)' : ''}
              </>
            ) : (
              <>Loading dashboard data…</>
            )}
          </div>
          <div className="flex flex-wrap gap-3">
            {sectionStates.map((s) => {
              const st = s?.meta?.status || (s.id === 'equity_curve' ? curveStatus : '')
              const upd = s?.meta?.cache_updated_at
              const updText = (typeof upd === 'string' && upd) ? ` @ ${formatDateTime(upd)}` : ''
              const text = `${s.key}: ${s.loaded ? 'Loaded' : 'Loading'}${st ? ` (${st})` : ''}${updText}`
              const cls = s.loaded ? 'text-green-700' : 'text-amber-700'
              return (
                <div key={s.id} className={cls}>{text}</div>
              )
            })}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <Card title="Portfolio Value" value={formatCurrency(summary?.portfolio_value)} sub={`Invested: ${formatCurrency(summary?.invested_value)}`} />
        <Card title="Total Profit" value={formatCurrency(summary?.total_profit)} valueClassName={pnClass(summary?.total_profit)} sub={`Realized: ${formatCurrency(summary?.realized)} | Unrealized: ${formatCurrency(summary?.unrealized)}`} />
        <Card title="Daily Change" value={formatCurrency(summary?.daily_change)} valueClassName={pnClass(summary?.daily_change)} />
        <Card title="Total Return %" value={formatPct(summary?.total_return_pct)} valueClassName={pnClass(summary?.total_return_pct)} />
        <Card title="Trades (A/C/P%)" value={`${summary?.total_trades ?? 0} / ${summary?.active_trades ?? 0} / ${summary?.profitable_trades_pct?.toFixed?.(2) ?? '0.00'}%`} sub={`Closed: ${summary?.closed_trades ?? 0}`} />
      </div>

      {chartData.length > 0 ? (
        <EquityChart data={chartData} />
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 h-80 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400">
          {curveStatus === 'warming' ? 'Loading equity curve…' : 'No equity curve data'}
        </div>
      )}

      {tlslHit.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
          <div className="font-semibold mb-3">TLSL Hit (Today)</div>
          <div className="flex flex-wrap gap-3">
            {tlslHit.map((h: any) => (
              <div key={`tlsl-${h.holding_id}`} className="border dark:border-gray-700 rounded px-3 py-2 text-sm flex items-center gap-3">
                <div className="font-semibold">{h.symbol}</div>
                <div>Last: {formatCurrency(h.last_price)}</div>
                <div>TLSL: {formatCurrency(h.tlsl_price)}</div>
                <button className="border dark:border-gray-700 rounded px-2 py-1" onClick={() => {
                  const pre = charts?.charts?.find((c: any) => c.holding_id === h.holding_id)
                  if (pre && Array.isArray(pre?.dates) && pre?.dates?.length > 0) {
                    setChartFor({ holding_id: h.holding_id, data: pre })
                    setSlDraft(String(pre.sl_price || 0))
                  } else {
                    void loadHoldingChart(h.holding_id, 90)
                  }
                }}>Open</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {slBreached.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
          <div className="font-semibold mb-3">SL Breached</div>
          <div className="flex flex-wrap gap-3">
            {slBreached.map((h: any) => (
              <div
                key={`sl-${h.holding_id}`}
                className={`border rounded px-3 py-2 text-sm flex items-center gap-3 dark:border-gray-700 ${h.sl_breached ? 'border-red-300 bg-red-50 dark:border-red-700 dark:bg-red-900/20' : h.sma23_breached ? 'border-violet-300 bg-violet-50 dark:border-violet-700 dark:bg-violet-900/20' : ''}`}
              >
                <div className="font-semibold">{h.symbol}</div>
                {h.sl_breached && (
                  <div className="px-2 py-0.5 rounded bg-red-100 text-red-700 border border-red-200 dark:bg-red-900/30 dark:text-red-200 dark:border-red-700">SL</div>
                )}
                {!h.sl_breached && h.sma23_breached && (
                  <div className="px-2 py-0.5 rounded bg-violet-100 text-violet-700 border border-violet-200 dark:bg-violet-900/30 dark:text-violet-200 dark:border-violet-700">SMA23</div>
                )}
                <div>Last: {formatCurrency(h.last_price)}</div>
                <div>{h.sl_breached ? `SL: ${formatCurrency(h.sl_price)}` : h.sma23_breached ? `SMA23: ${formatCurrency(h.sma23)}` : ''}</div>
                <button className="border dark:border-gray-700 rounded px-2 py-1" onClick={() => {
                  const pre = charts?.charts?.find((c: any) => c.holding_id === h.holding_id)
                  if (pre && Array.isArray(pre?.dates) && pre?.dates?.length > 0) {
                    setChartFor({ holding_id: h.holding_id, data: pre })
                    setSlDraft(String(pre.sl_price || 0))
                  } else {
                    void loadHoldingChart(h.holding_id, 90)
                  }
                }}>Open</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {targetsHit.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
          <div className="font-semibold mb-3">Targets Hit</div>
          <div className="flex flex-wrap gap-3">
            {targetsHit.map((h: any) => {
              const label = h.r3_hit ? 'R3' : h.r2_hit ? 'R2' : 'R1'
              return (
                <div key={`tgt-${h.holding_id}`} className="border dark:border-gray-700 rounded px-3 py-2 text-sm flex items-center gap-3">
                  <div className="font-semibold">{h.symbol}</div>
                  <div className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-200 dark:border-emerald-700">{label}</div>
                  <div>Last: {formatCurrency(h.last_price)}</div>
                  <button className="border dark:border-gray-700 rounded px-2 py-1" onClick={() => {
                    const pre = charts?.charts?.find((c: any) => c.holding_id === h.holding_id)
                    if (pre && Array.isArray(pre?.dates) && pre?.dates?.length > 0) {
                      setChartFor({ holding_id: h.holding_id, data: pre })
                      setSlDraft(String(pre.sl_price || 0))
                    } else {
                      void loadHoldingChart(h.holding_id, 90)
                    }
                  }}>Open</button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="font-semibold mb-3">Account Wise</div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b dark:border-gray-700">
                <th className="py-2">Account</th>
                <th className="py-2">Broker</th>
                <th className="py-2">Portfolio Value</th>
                <th className="py-2">Invested Value</th>
                <th className="py-2">Total Profit</th>
                <th className="py-2">Return %</th>
              </tr>
            </thead>
            <tbody>
              {acct?.accounts?.map((a) => (
                <tr key={a.account_id} className="border-b dark:border-gray-700 last:border-b-0">
                  <td className="py-2">{a.name}</td>
                  <td className="py-2">{a.broker || '-'}</td>
                  <td className="py-2">{formatCurrency(a.portfolio_value)}</td>
                  <td className="py-2">{formatCurrency(a.invested_value)}</td>
                  <td className={`py-2 ${pnClass(a.total_profit)}`}>{formatCurrency(a.total_profit)}</td>
                  <td className={`py-2 ${pnClass(a.return_pct)}`}>{formatPct(a.return_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="font-semibold mb-3">Per-Holding P/L</div>
        <div className="grid grid-cols-1 md:grid-cols-6 gap-3 mb-4">
          <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" value={acctFilter} onChange={e => setAcctFilter(e.target.value)}>
            <option value="">All Accounts</option>
            {accountOptions.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option value="all">All Holdings</option>
            <option value="active">Active Only</option>
            <option value="sold">Sold Only</option>
          </select>
          <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Filter Symbol" value={symbolFilter} onChange={e => setSymbolFilter(e.target.value)} />
          <div className="flex gap-2">
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 w-1/2" placeholder="MV min" value={mvMin} onChange={e => setMvMin(e.target.value)} />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 w-1/2" placeholder="MV max" value={mvMax} onChange={e => setMvMax(e.target.value)} />
          </div>
          <div className="flex gap-2">
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 w-1/2" placeholder="Inv min" value={invMin} onChange={e => setInvMin(e.target.value)} />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 w-1/2" placeholder="Inv max" value={invMax} onChange={e => setInvMax(e.target.value)} />
          </div>
          <div className="flex gap-2">
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 w-1/2" placeholder="Unreal min" value={unrMin} onChange={e => setUnrMin(e.target.value)} />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 w-1/2" placeholder="Unreal max" value={unrMax} onChange={e => setUnrMax(e.target.value)} />
          </div>
          <div className="flex gap-2">
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 w-1/2" placeholder="Realized min" value={rrMin} onChange={e => setRrMin(e.target.value)} />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 w-1/2" placeholder="Realized max" value={rrMax} onChange={e => setRrMax(e.target.value)} />
          </div>
          <div className="flex gap-2 md:col-span-2">
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 w-1/2" placeholder="Daily min" value={dpMin} onChange={e => setDpMin(e.target.value)} />
            <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 w-1/2" placeholder="Daily max" value={dpMax} onChange={e => setDpMax(e.target.value)} />
            <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" value={sortKey} onChange={e => setSortKey(e.target.value)}>
              <option value="account_name">Account</option>
              <option value="symbol">Symbol</option>
              <option value="strategy">Strategy</option>
              <option value="market_value">Market Value</option>
              <option value="invested_value">Invested</option>
              <option value="unrealized_pl">Unrealized P/L</option>
              <option value="realized_pl">Realized P/L</option>
              <option value="daily_pl">Daily P/L</option>
              <option value="return_pct">Return %</option>
            </select>
            <button className="border dark:border-gray-700 rounded px-3 py-2" onClick={() => setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}>{sortDir === 'asc' ? 'Asc' : 'Desc'}</button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b dark:border-gray-700">
                <th className="py-2">Account</th>
                <th className="py-2">Symbol</th>
                <th className="py-2">Strategy</th>
                <th className="py-2">Qty</th>
                <th className="py-2">Avg Price</th>
                <th className="py-2">Last</th>
                <th className="py-2">Market Value</th>
                <th className="py-2">Invested Value</th>
                <th className="py-2">Return %</th>
                <th className="py-2">Unrealized P/L</th>
                <th className="py-2">Realized P/L</th>
                <th className="py-2">Daily P/L</th>
                <th className="py-2">SL</th>
                <th className="py-2">Chart</th>
              </tr>
            </thead>
            <tbody>
              {filteredHoldings.map((h: any) => (
                <tr key={h.holding_id} className="border-b dark:border-gray-700 last:border-b-0">
                  <td className="py-2">{h.account_name}</td>
                  <td className="py-2">
                    <div className="flex items-center gap-2">
                      <span title={holdingNotes[h.holding_id] || ''}>{h.symbol}</span>
                      {!!holdingNotes[h.holding_id] && (
                        <button
                          type="button"
                          className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                          title={holdingNotes[h.holding_id]}
                          onClick={() => {
                            const note = holdingNotes[h.holding_id]
                            if (note) setNoteModal({ symbol: h.symbol, note })
                          }}
                        >
                          <StickyNote size={16} />
                        </button>
                      )}
                    </div>
                  </td>
                  <td className="py-2">{h.strategy || '-'}</td>
                  <td className="py-2">{h.quantity}</td>
                  <td className="py-2">{formatCurrency(h.average_price)}</td>
                  <td className="py-2">{formatCurrency(h.last_price)}</td>
                  <td className="py-2">{formatCurrency(h.market_value)}</td>
                  <td className="py-2">{formatCurrency(h.invested_value)}</td>
                  <td className={`py-2 ${pnClass(h.return_pct)}`}>{formatPct(h.return_pct)}</td>
                  <td className={`py-2 ${pnClass(h.unrealized_pl)}`}>{formatCurrency(h.unrealized_pl)}</td>
                  <td className={`py-2 ${pnClass(h.realized_pl)}`}>{formatCurrency(h.realized_pl)}</td>
                  <td className={`py-2 ${pnClass(h.daily_pl)}`}>{formatCurrency(h.daily_pl)}</td>
                  <td className="py-2">{h.sl_price ? formatCurrency(h.sl_price) : '-'}</td>
                  <td className="py-2">
                    {h.quantity > 0 && (
                      <button className="border dark:border-gray-700 rounded px-3 py-1" onClick={() => {
                        const pre = charts?.charts?.find((c: any) => c.holding_id === h.holding_id)
                        if (pre && Array.isArray(pre?.dates) && pre?.dates?.length > 0) {
                          setChartFor({ holding_id: h.holding_id, data: pre })
                          setSlDraft(String(pre.sl_price || 0))
                        } else {
                          void loadHoldingChart(h.holding_id, 90)
                        }
                      }}>Open</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {chartFor && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onMouseDown={(e) => { if (e.currentTarget === e.target) setChartFor(null) }}
        >
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 w-full max-w-5xl">
            <div className="flex items-center justify-between mb-3">
              <div className="font-semibold">{chartFor.data.symbol} — Last 90d</div>
              <div className="flex gap-3 items-center">
                <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={useHeikin} onChange={e => setUseHeikin(e.target.checked)} /> Heikin-Ashi</label>
                <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={showVolume} onChange={e => setShowVolume(e.target.checked)} /> Volume</label>
                <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={showRSI} onChange={e => setShowRSI(e.target.checked)} /> RSI</label>
                <button className="border dark:border-gray-700 rounded px-3 py-1" onClick={() => setChartFor(null)}>Close</button>
              </div>
            </div>
            {!!holdingNotes[chartFor.holding_id] && (
              <div className="mb-3 text-sm text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-gray-900/40 border border-gray-200 dark:border-gray-700 rounded p-3 whitespace-pre-wrap">
                {holdingNotes[chartFor.holding_id]}
              </div>
            )}
            <LWCHoldingChart data={chartFor.data} useHeikin={useHeikin} showVolume={showVolume} showRSI={showRSI} />
            <div className="mt-3 flex items-center gap-2 text-sm">
              <label>SL:</label>
              <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1 w-28" type="number" step="0.05" value={slDraft} onChange={e => setSlDraft(e.target.value)} />
              <button className="border dark:border-gray-700 rounded px-3 py-1 disabled:opacity-50" disabled={slSaving} onClick={async () => {
                if (!chartFor) return
                setSlSaving(true)
                try {
                  const val = parseFloat(slDraft || '0')
                  const newSl = isFinite(val) ? val : 0
                  const hid = chartFor.holding_id
                  await api.patch(`/holdings/${hid}`, { sl_price: newSl })

                  setHoldings((prev) => {
                    const rows = (prev?.holdings || []).map((h: any) => {
                      if (h.holding_id !== hid) return h
                      const last = Number(h.last_price ?? 0)
                      const breached = newSl > 0 && last > 0 && last <= newSl
                      return { ...h, sl_price: newSl, sl_breached: breached }
                    })
                    return prev ? { ...prev, holdings: rows } : prev
                  })

                  setCharts((prev) => {
                    if (!prev || !Array.isArray(prev.charts)) return prev
                    const updated = prev.charts.map((c: any) => (c.holding_id === hid ? { ...c, sl_price: newSl } : c))
                    return { ...prev, charts: updated }
                  })

                  setChartFor(null)
                } finally {
                  setSlSaving(false)
                }
              }}>Save SL</button>
            </div>
          </div>
        </div>
      )}

      {noteModal && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onMouseDown={(e) => { if (e.currentTarget === e.target) setNoteModal(null) }}
        >
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 w-full max-w-xl">
            <div className="flex items-center justify-between mb-3">
              <div className="font-semibold">{noteModal.symbol} — Trade Note</div>
              <button className="border dark:border-gray-700 rounded px-3 py-1" onClick={() => setNoteModal(null)}>Close</button>
            </div>
            <div className="text-sm text-gray-700 dark:text-gray-200 whitespace-pre-wrap">
              {noteModal.note}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
