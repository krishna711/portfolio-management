import { useEffect, useMemo, useState } from 'react'
import api from '../api/client'
import LWCHoldingChart from '../charts/LWCHoldingChart'

export default function Screeners() {
  const [list, setList] = useState<{ scanners: { key: string; title: string; latest_for_date?: string | null; latest_rows?: number }[] } | null>(null)
  const [active, setActive] = useState<string>('ha-daily-buy-ipo')
  const [loading, setLoading] = useState<boolean>(false)
  const [rows, setRows] = useState<any[]>([])
  const [forDate, setForDate] = useState<string>('')
  const [fromCache, setFromCache] = useState<boolean>(true)
  const [error, setError] = useState<string>('')
  const [debugInfo, setDebugInfo] = useState<any>(null)
  const [dates, setDates] = useState<{date: string; rows: number}[]>([])
  const [selectedDate, setSelectedDate] = useState<string>('')
  const [chartOpen, setChartOpen] = useState<boolean>(false)
  const [chartData, setChartData] = useState<any | null>(null)
  const [useHeikin, setUseHeikin] = useState<boolean>(false)
  const [showVolume, setShowVolume] = useState<boolean>(true)
  const [showRSI, setShowRSI] = useState<boolean>(true)

  useEffect(() => { (async () => { const res = await api.get('/screeners/'); setList(res.data) })() }, [])

  const load = async (key: string, force = false, date?: string) => {
    setLoading(true)
    setError('')
    try {
      const p = new URLSearchParams()
      if (force) { p.set('force','1'); p.set('driver','auto') }
      p.set('debug','1')
      if (date) p.set('date', date)
      const res = await api.get(`/screeners/${key}?${p.toString()}`)
      const d = res.data || {}
      setRows(Array.isArray(d.rows) ? d.rows : [])
      setForDate(d.for_date || '')
      setFromCache(!!d.from_cache)
      setDebugInfo(d.debug || null)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load screener')
    } finally { setLoading(false) }
  }

  const loadDates = async (key: string) => {
    try {
      const r = await api.get(`/screeners/${key}/dates`)
      const d = r.data || {}
      setDates(Array.isArray(d.dates) ? d.dates : [])
    } catch {}
  }

  useEffect(() => { if (active) { loadDates(active); load(active) } }, [active])

  const openChart = async (symbol: string) => {
    try {
      const r = await api.get(`/screeners/stock_chart?symbol=${encodeURIComponent(symbol)}&days=90`)
      setChartData(r.data)
      setChartOpen(true)
    } catch {}
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="text-xl font-semibold">Screeners</div>
      </div>

      {chartOpen && chartData && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onMouseDown={(e)=>{ if (e.currentTarget===e.target) setChartOpen(false) }}>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 w-full max-w-5xl">
            <div className="flex items-center justify-between mb-3">
              <div className="font-semibold">{chartData.symbol} — Last 90d</div>
              <div className="flex gap-3 items-center">
                <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={useHeikin} onChange={e => setUseHeikin(e.target.checked)} /> Heikin-Ashi</label>
                <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={showVolume} onChange={e => setShowVolume(e.target.checked)} /> Volume</label>
                <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={showRSI} onChange={e => setShowRSI(e.target.checked)} /> RSI</label>
                <button className="border dark:border-gray-700 rounded px-3 py-1" onClick={() => setChartOpen(false)}>Close</button>
              </div>
            </div>
            <LWCHoldingChart data={chartData} useHeikin={useHeikin} showVolume={showVolume} showRSI={showRSI} />
          </div>
        </div>
      )}
      <div className="flex gap-2 flex-wrap">
        {list?.scanners?.map((s) => (
          <button key={s.key} className={`px-3 py-1.5 border rounded ${active===s.key?'bg-gray-900 text-white':''}`} onClick={() => setActive(s.key)}>
            {s.title}{s.latest_for_date?` • ${s.latest_for_date}`:''}
          </button>
        ))}
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
        <div className="flex items-center justify-between mb-3 text-sm">
          <div className="flex items-center gap-2">
            <span className="font-semibold">{list?.scanners?.find(x=>x.key===active)?.title}</span>
            <span>— {forDate} {fromCache ? '(cached)' : ''}</span>
          </div>
          <div className="flex items-center gap-2">
            <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1" value={selectedDate} onChange={e => { const v = e.target.value; setSelectedDate(v); load(active, false, v || undefined) }}>
              <option value="">Latest</option>
              {dates.map(d => (<option key={d.date} value={d.date}>{d.date} ({d.rows})</option>))}
            </select>
            <button className="border dark:border-gray-700 rounded px-2 py-1" disabled={loading} onClick={() => load(active, false)}>Refresh</button>
            <button className="border dark:border-gray-700 rounded px-2 py-1" disabled={loading} onClick={() => load(active, true)}>Force Fetch</button>
            <span>{loading ? 'Loading...' : `${rows.length} rows`}</span>
          </div>
        </div>
        {error && <div className="text-red-600 text-sm mb-2">{error}</div>}
        {debugInfo && (
          <div className="text-xs text-gray-500 mb-2">
            <span className="mr-2">used_json_api: {String(debugInfo.used_json_api)}</span>
            {typeof debugInfo.json_rows !== 'undefined' && <span className="mr-2">json_rows: {debugInfo.json_rows}</span>}
            {typeof debugInfo.fallback_rows !== 'undefined' && <span className="mr-2">fallback_rows: {debugInfo.fallback_rows}</span>}
            {typeof debugInfo.got_token !== 'undefined' && <span className="mr-2">got_token: {String(debugInfo.got_token)}</span>}
            {typeof debugInfo.atlas_query_len !== 'undefined' && <span className="mr-2">atlas_query_len: {debugInfo.atlas_query_len}</span>}
            {typeof debugInfo.used_scan_id !== 'undefined' && <span className="mr-2">used_scan_id: {String(debugInfo.used_scan_id)}</span>}
            {typeof debugInfo.http_status !== 'undefined' && <span className="mr-2">http_status: {debugInfo.http_status}</span>}
            {typeof debugInfo.cf_used !== 'undefined' && <span className="mr-2">cf_used: {String(debugInfo.cf_used)}</span>}
            {typeof debugInfo.cf_rows !== 'undefined' && <span className="mr-2">cf_rows: {debugInfo.cf_rows}</span>}
            {typeof debugInfo.resp_msg !== 'undefined' && <span className="mr-2">resp_msg: {String(debugInfo.resp_msg)}</span>}
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b dark:border-gray-700">
                <th className="py-2 px-2">Sr.</th>
                <th className="py-2 px-2">Stock Name</th>
                <th className="py-2 px-2">Symbol</th>
                <th className="py-2 px-2">Links</th>
                <th className="py-2 px-2">% Chg</th>
                <th className="py-2 px-2">Price</th>
                <th className="py-2 px-2">Volume</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, idx) => (
                <tr key={`${r.symbol}-${idx}`} className="border-b dark:border-gray-700 last:border-b-0">
                  <td className="py-2 px-2">{r.sr ?? idx+1}</td>
                  <td className="py-2 px-2 font-semibold"><a href={`https://chartink.com/stocks/${(r.stock_name||'').toLowerCase().replace(/\s+/g,'-')}.html`} target="_blank" rel="noreferrer">{r.stock_name}</a></td>
                  <td className="py-2 px-2 font-semibold"><a href={`https://chartink.com/stocks/${(r.symbol||'').toUpperCase()}.html`} target="_blank" rel="noreferrer">{r.symbol}</a></td>
                  <td className="py-2 px-2 space-x-2">
                    {r.pf_url && <a className="text-blue-600 hover:underline" href={r.pf_url} target="_blank" rel="noreferrer">P&F</a>}
                    {r.fa_url && <a className="text-blue-600 hover:underline" href={r.fa_url} target="_blank" rel="noreferrer">F.A</a>}
                    <button className="border dark:border-gray-700 rounded px-2 py-0.5" onClick={() => openChart(r.symbol)}>Chart</button>
                  </td>
                  <td className={`py-2 px-2 ${Number(r.chg_pct)>0?'text-green-600':Number(r.chg_pct)<0?'text-red-600':''}`}>{r.chg_pct!=null?`${Number(r.chg_pct).toFixed(2)}%`:'-'}</td>
                  <td className="py-2 px-2">{r.price!=null?Number(r.price).toFixed(2):'-'}</td>
                  <td className="py-2 px-2">{r.volume!=null?Number(r.volume).toLocaleString(): '-'}</td>
                </tr>
              ))}
              {rows.length===0 && (
                <tr><td colSpan={7} className="text-center py-6 text-gray-500">No data</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
