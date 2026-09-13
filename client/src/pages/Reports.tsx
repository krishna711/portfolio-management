import { useEffect, useMemo, useState } from 'react'
import api from '../api/client'
import Card from '../components/Card'

function formatCurrency(n: number | null | undefined) {
  if (n == null) return '-'
  return n.toLocaleString(undefined, { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })
}

function pnClass(n: number | null | undefined) {
  if (n == null) return ''
  if (n > 0) return 'text-green-600'
  if (n < 0) return 'text-red-600'
  return ''
}

export default function Reports() {
  type SortKey = 'sell_date' | 'holding_days' | 'account_name' | 'symbol' | 'investment' | 'realized_profit'

  const [startYear, setStartYear] = useState<number>(() => {
    const d = new Date()
    const y = d.getFullYear()
    const m = d.getMonth() + 1
    return m >= 4 ? y : y - 1
  })
  const [report, setReport] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [accountFilter, setAccountFilter] = useState<string>('')
  const [sortKey, setSortKey] = useState<SortKey>('sell_date')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const years = useMemo(() => {
    const now = new Date()
    const y = now.getFullYear()
    const m = now.getMonth() + 1
    const current = m >= 4 ? y : y - 1
    const out: number[] = []
    for (let i = 0; i < 8; i++) out.push(current - i)
    return out
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        setLoading(true)
        setError(null)
        const res = await api.get(`/reports/financial_year?start_year=${startYear}`)
        if (cancelled) return
        setReport(res.data)
      } catch (e: any) {
        if (cancelled) return
        setError(e?.response?.data?.detail || 'Failed to load report')
        setReport(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [startYear])

  const accounts: any[] = Array.isArray(report?.accounts) ? report.accounts : []
  const trades: any[] = Array.isArray(report?.trades) ? report.trades : []

  const filteredTrades = useMemo(() => {
    if (!accountFilter) return trades
    const aid = Number(accountFilter)
    return trades.filter((t: any) => Number(t?.account_id) === aid)
  }, [trades, accountFilter])

  const sortedTrades = useMemo(() => {
    const rows = [...filteredTrades]
    const dir = sortDir === 'asc' ? 1 : -1

    const getNum = (v: any) => {
      const n = Number(v)
      return Number.isFinite(n) ? n : null
    }

    rows.sort((a: any, b: any) => {
      if (sortKey === 'holding_days') {
        const av = getNum(a?.holding_days)
        const bv = getNum(b?.holding_days)
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        return (av - bv) * dir
      }
      if (sortKey === 'investment') {
        const av = getNum(a?.investment) ?? 0
        const bv = getNum(b?.investment) ?? 0
        return (av - bv) * dir
      }
      if (sortKey === 'realized_profit') {
        const av = getNum(a?.realized_profit) ?? 0
        const bv = getNum(b?.realized_profit) ?? 0
        return (av - bv) * dir
      }
      if (sortKey === 'account_name') {
        return String(a?.account_name || '').localeCompare(String(b?.account_name || '')) * dir
      }
      if (sortKey === 'symbol') {
        return String(a?.symbol || '').localeCompare(String(b?.symbol || '')) * dir
      }
      // default: sort by sell_date desc/asc
      return String(a?.sell_date || '').localeCompare(String(b?.sell_date || '')) * dir
    })
    return rows
  }, [filteredTrades, sortKey, sortDir])

  const toggleSort = (k: Exclude<SortKey, 'sell_date'>) => {
    if (sortKey === k) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortKey(k)
    if (k === 'account_name' || k === 'symbol') setSortDir('asc')
    else setSortDir('desc')
  }

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <div className="text-lg font-semibold">Reports</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              Financial Year report (Realized profit + all trades)
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="text-sm text-gray-600 dark:text-gray-400">Financial Year</div>
            <select
              className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2"
              value={startYear}
              onChange={(e) => setStartYear(Number(e.target.value))}
            >
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}-{y + 1}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
        {loading && <div className="mt-3 text-sm text-gray-600 dark:text-gray-400">Loading...</div>}

        {!!report && (
          <div className="mt-3 text-sm text-gray-600 dark:text-gray-400">
            Range: {report?.start_date} to {report?.end_date}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card
          title={`Realized Profit (FY ${report?.financial_year || `${startYear}-${startYear + 1}`})`}
          value={formatCurrency(report?.total_realized_profit)}
          valueClassName={pnClass(report?.total_realized_profit)}
        />
        <Card title="Accounts" value={String(accounts.length)} />
        <Card title="Trades" value={String(trades.length)} />
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="font-semibold mb-3">Account-wise Realized Profit</div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b dark:border-gray-700">
                <th className="py-2">Account</th>
                <th className="py-2">Broker</th>
                <th className="py-2">Trades</th>
                <th className="py-2">Realized Profit</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a: any) => (
                <tr key={a.account_id} className="border-b dark:border-gray-700 last:border-b-0">
                  <td className="py-2">{a.account_name}</td>
                  <td className="py-2">{a.broker || '-'}</td>
                  <td className="py-2">{Number(a.trades ?? 0).toLocaleString()}</td>
                  <td className={`py-2 ${pnClass(a.realized_profit)}`}>{formatCurrency(a.realized_profit)}</td>
                </tr>
              ))}
              {!accounts.length && (
                <tr>
                  <td className="py-3 text-sm text-gray-600 dark:text-gray-400" colSpan={4}>
                    No accounts/trades found in this financial year.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-3">
          <div className="font-semibold">Trades in Financial Year</div>
          <div className="flex items-center gap-2">
            <div className="text-sm text-gray-600 dark:text-gray-400">Account</div>
            <select
              className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2"
              value={accountFilter}
              onChange={(e) => setAccountFilter(e.target.value)}
            >
              <option value="">All</option>
              {accounts.map((a: any) => (
                <option key={a.account_id} value={String(a.account_id)}>
                  {a.account_name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b dark:border-gray-700">
                <th className="py-2">Buy Date</th>
                <th className="py-2">Sell Date</th>
                <th className="py-2">
                  <button type="button" className="hover:underline" onClick={() => toggleSort('holding_days')}>Holding Days</button>
                </th>
                <th className="py-2">
                  <button type="button" className="hover:underline" onClick={() => toggleSort('account_name')}>Account</button>
                </th>
                <th className="py-2">
                  <button type="button" className="hover:underline" onClick={() => toggleSort('symbol')}>Symbol</button>
                </th>
                <th className="py-2">Qty</th>
                <th className="py-2">Sell Price</th>
                <th className="py-2">
                  <button type="button" className="hover:underline" onClick={() => toggleSort('investment')}>Investment</button>
                </th>
                <th className="py-2">
                  <button type="button" className="hover:underline" onClick={() => toggleSort('realized_profit')}>Realized</button>
                </th>
                <th className="py-2">Strategy</th>
                <th className="py-2">Notes</th>
              </tr>
            </thead>
            <tbody>
              {sortedTrades.map((t: any) => (
                <tr key={t.transaction_id || `${t.account_id}-${t.holding_id}-${t.sell_date}-${t.investment}`} className="border-b dark:border-gray-700 last:border-b-0">
                  <td className="py-2">{t.buy_date || '-'}</td>
                  <td className="py-2">{t.sell_date || '-'}</td>
                  <td className="py-2">{t.holding_days ?? '-'}</td>
                  <td className="py-2">{t.account_name || '-'}</td>
                  <td className="py-2">{t.symbol}</td>
                  <td className="py-2">{Number(t.quantity).toLocaleString()}</td>
                  <td className="py-2">{formatCurrency(t.price)}</td>
                  <td className="py-2">{formatCurrency(t.investment)}</td>
                  <td className={`py-2 ${pnClass(t.realized_profit)}`}>{formatCurrency(t.realized_profit)}</td>
                  <td className="py-2">{t.strategy || '-'}</td>
                  <td className="py-2 max-w-[360px] truncate" title={t.notes || ''}>{t.notes || '-'}</td>
                </tr>
              ))}
              {!sortedTrades.length && (
                <tr>
                  <td className="py-3 text-sm text-gray-600 dark:text-gray-400" colSpan={11}>
                    No trades found for this selection.
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
