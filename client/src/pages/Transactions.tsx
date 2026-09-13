import { FormEvent, useEffect, useMemo, useState } from 'react'
import api from '../api/client'

export default function Transactions() {
  const [accounts, setAccounts] = useState<any[]>([])
  const [selectedAccount, setSelectedAccount] = useState<number | null>(null)
  const [holdings, setHoldings] = useState<any[]>([])
  const [txns, setTxns] = useState<any[]>([])
  const [strategies, setStrategies] = useState<any[]>([])

  const [symbol, setSymbol] = useState('')
  const [type, setType] = useState<'Buy' | 'Sell'>('Buy')
  const [qty, setQty] = useState<number>(0)
  const [price, setPrice] = useState<number>(0)
  const [date, setDate] = useState<string>('')
  const [strategyId, setStrategyId] = useState<number | null>(null)
  const [notes, setNotes] = useState<string>('')

  // Holding edit state
  const [editingHoldingId, setEditingHoldingId] = useState<number | null>(null)
  const [editHoldingSymbol, setEditHoldingSymbol] = useState<string>('')

  // Transaction edit state
  const [editingTxnId, setEditingTxnId] = useState<number | null>(null)
  const [editTxnType, setEditTxnType] = useState<'Buy' | 'Sell'>('Buy')
  const [editTxnQty, setEditTxnQty] = useState<number>(0)
  const [editTxnPrice, setEditTxnPrice] = useState<number>(0)
  const [editTxnDate, setEditTxnDate] = useState<string>('')
  const [editTxnStrategyId, setEditTxnStrategyId] = useState<number | null>(null)
  const [editTxnNotes, setEditTxnNotes] = useState<string>('')

  useEffect(() => {
    (async () => {
      try {
        const [res, sr] = await Promise.all([
          api.get('/accounts/'),
          api.get('/strategies/'),
        ])
        const rows = Array.isArray(res.data) ? res.data : []
        setAccounts(rows)
        const srows = Array.isArray(sr.data) ? sr.data : []
        setStrategies(srows)
        const swing = srows.find((x: any) => x?.name === 'Swing')
        if (swing?.id) setStrategyId(swing.id)
        else if (srows?.[0]?.id) setStrategyId(srows[0].id)
        if (rows.length && (selectedAccount === null)) {
          const id = rows[0].id as number
          setSelectedAccount(id)
          await loadData(id)
        }
      } catch (e) {
        console.error('Failed to load accounts', e)
        setAccounts([])
      }
    })()
  }, [])

  const loadData = async (accountId: number) => {
    try {
      const [h, t] = await Promise.all([
        api.get(`/holdings/?account_id=${accountId}`),
        api.get(`/transactions/?account_id=${accountId}`),
      ])
      setHoldings(Array.isArray(h.data) ? h.data : [])
      setTxns(Array.isArray(t.data) ? t.data : [])
    } catch (e) {
      console.error('Failed to load holdings/transactions', e)
      setHoldings([])
      setTxns([])
    }
  }

  useEffect(() => {
    if (selectedAccount) loadData(selectedAccount)
  }, [selectedAccount])

  const holdingMap = useMemo(() => Object.fromEntries(holdings.map((h: any) => [h.id, h.symbol])), [holdings])
  const strategyMap = useMemo(() => Object.fromEntries(strategies.map((s: any) => [s.id, s.name])), [strategies])

  const holdingNoteMap = useMemo(() => {
    const by: Record<string, string> = {}
    const sorted = [...txns].sort((a: any, b: any) => {
      const ad = String(a.transaction_date || '')
      const bd = String(b.transaction_date || '')
      if (ad !== bd) return ad.localeCompare(bd)
      return Number(a.id || 0) - Number(b.id || 0)
    })
    for (const t of sorted) {
      if (String(t.transaction_type) !== 'Buy') continue
      const hid = String(t.holding_id)
      const n = (t.notes || '').trim()
      if (n && !by[hid]) by[hid] = n
    }
    return by
  }, [txns])

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!selectedAccount) return
    const payload: any = { account_id: selectedAccount, symbol, transaction_type: type, quantity: Number(qty), price: Number(price) }
    if (date) payload.transaction_date = date
    if (strategyId) payload.strategy_id = strategyId
    if (notes.trim()) payload.notes = notes
    await api.post('/transactions/', payload)
    setSymbol('')
    setQty(0)
    setPrice(0)
    setDate('')
    setNotes('')
    if (selectedAccount) await loadData(selectedAccount)
  }

  // Holding actions
  const onHoldEdit = (h: any) => {
    setEditingHoldingId(h.id)
    setEditHoldingSymbol(h.symbol)
  }
  const onHoldCancel = () => {
    setEditingHoldingId(null)
    setEditHoldingSymbol('')
  }
  const onHoldSave = async (id: number) => {
    await api.patch(`/holdings/${id}`, { symbol: editHoldingSymbol })
    onHoldCancel()
    if (selectedAccount) await loadData(selectedAccount)
  }
  const onHoldDelete = async (id: number) => {
    const ok = window.confirm('Delete holding and all its transactions?')
    if (!ok) return
    await api.delete(`/holdings/${id}`)
    if (selectedAccount) await loadData(selectedAccount)
  }

  // Transaction actions
  const onTxnEdit = (t: any) => {
    setEditingTxnId(t.id)
    setEditTxnType(t.transaction_type)
    setEditTxnQty(t.quantity)
    setEditTxnPrice(t.price)
    setEditTxnDate(t.transaction_date)
    setEditTxnStrategyId((t.strategy_id ?? null) as any)
    setEditTxnNotes(t.notes || '')
  }
  const onTxnCancel = () => {
    setEditingTxnId(null)
  }
  const onTxnSave = async (id: number) => {
    const payload: any = {
      transaction_type: editTxnType,
      quantity: Number(editTxnQty),
      price: Number(editTxnPrice),
      transaction_date: editTxnDate || undefined,
    }
    if (editTxnStrategyId) payload.strategy_id = editTxnStrategyId
    payload.notes = editTxnNotes
    await api.patch(`/transactions/${id}`, payload)
    setEditingTxnId(null)
    if (selectedAccount) await loadData(selectedAccount)
  }
  const onTxnDelete = async (id: number) => {
    const ok = window.confirm('Delete this transaction? Holding quantities will be recomputed.')
    if (!ok) return
    await api.delete(`/transactions/${id}`)
    if (selectedAccount) await loadData(selectedAccount)
  }

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="font-semibold mb-3">Add Transaction</div>
        <form onSubmit={onSubmit} className="grid grid-cols-1 md:grid-cols-8 gap-3">
          <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" value={selectedAccount ?? ''} onChange={e => setSelectedAccount(Number(e.target.value) || null)} required>
            <option value="">Select Account</option>
            {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Symbol (e.g., TCS.NS)" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} required />
          <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" value={type} onChange={e => setType(e.target.value as any)}>
            <option value="Buy">Buy</option>
            <option value="Sell">Sell</option>
          </select>
          <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" value={strategyId ?? ''} onChange={e => setStrategyId(Number(e.target.value) || null)}>
            <option value="">Strategy</option>
            {strategies.map((s) => (<option key={s.id} value={s.id}>{s.name}</option>))}
          </select>
          <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Quantity" type="number" step="0.01" value={qty} onChange={e => setQty(Number(e.target.value))} required />
          <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Price" type="number" step="0.01" value={price} onChange={e => setPrice(Number(e.target.value))} required />
          <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" type="date" value={date} onChange={e => setDate(e.target.value)} />
          <textarea className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2 md:col-span-8" placeholder="Notes" value={notes} onChange={e => setNotes(e.target.value)} rows={2} />
          <div className="md:col-span-8">
            <button disabled={!selectedAccount} className="bg-gray-900 text-white px-4 py-2 rounded">Create</button>
          </div>
        </form>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
          <div className="font-semibold mb-3">Holdings</div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b dark:border-gray-700">
                  <th className="py-2">Symbol</th>
                  <th className="py-2">Qty</th>
                  <th className="py-2">Avg Price</th>
                  <th className="py-2">Total Cost</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map(h => (
                  <tr key={h.id} className="border-b dark:border-gray-700 last:border-b-0">
                    <td className="py-2">
                      {editingHoldingId === h.id ? (
                        <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1" value={editHoldingSymbol} onChange={e => setEditHoldingSymbol(e.target.value.toUpperCase())} />
                      ) : (
                        <span title={holdingNoteMap[String(h.id)] || ''} className={holdingNoteMap[String(h.id)] ? 'cursor-help' : ''}>{h.symbol}</span>
                      )}
                    </td>
                    <td className="py-2">{h.quantity}</td>
                    <td className="py-2">{h.average_price.toFixed(2)}</td>
                    <td className="py-2">{h.total_cost.toFixed(2)}</td>
                    <td className="py-2">
                      {editingHoldingId === h.id ? (
                        <div className="flex gap-2">
                          <button className="px-3 py-1 bg-gray-900 text-white rounded" onClick={() => onHoldSave(h.id)}>Save</button>
                          <button className="px-3 py-1 border dark:border-gray-700 rounded" onClick={onHoldCancel}>Cancel</button>
                        </div>
                      ) : (
                        <div className="flex gap-2">
                          <button className="px-3 py-1 border dark:border-gray-700 rounded" onClick={() => onHoldEdit(h)}>Edit</button>
                          <button className="px-3 py-1 border dark:border-gray-700 rounded text-red-600" onClick={() => onHoldDelete(h.id)}>Delete</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
          <div className="font-semibold mb-3">Transactions</div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b dark:border-gray-700">
                  <th className="py-2">Date</th>
                  <th className="py-2">Type</th>
                  <th className="py-2">Symbol</th>
                  <th className="py-2">Strategy</th>
                  <th className="py-2">Qty</th>
                  <th className="py-2">Price</th>
                  <th className="py-2">Total</th>
                  <th className="py-2">Realized P/L</th>
                  <th className="py-2">Notes</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {txns.map(t => (
                  <tr key={t.id} className="border-b dark:border-gray-700 last:border-b-0">
                    <td className="py-2">
                      {editingTxnId === t.id ? (
                        <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1" type="date" value={editTxnDate} onChange={e => setEditTxnDate(e.target.value)} />
                      ) : (
                        t.transaction_date
                      )}
                    </td>
                    <td className="py-2">
                      {editingTxnId === t.id ? (
                        <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1" value={editTxnType} onChange={e => setEditTxnType(e.target.value as any)}>
                          <option value="Buy">Buy</option>
                          <option value="Sell">Sell</option>
                        </select>
                      ) : (
                        t.transaction_type
                      )}
                    </td>
                    <td className="py-2">{holdingMap[t.holding_id]}</td>
                    <td className="py-2">
                      {editingTxnId === t.id ? (
                        <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1" value={editTxnStrategyId ?? ''} onChange={e => setEditTxnStrategyId(Number(e.target.value) || null)}>
                          <option value="">-</option>
                          {strategies.map((s) => (<option key={s.id} value={s.id}>{s.name}</option>))}
                        </select>
                      ) : (
                        strategyMap[t.strategy_id] || '-'
                      )}
                    </td>
                    <td className="py-2">
                      {editingTxnId === t.id ? (
                        <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1" type="number" step="0.01" value={editTxnQty} onChange={e => setEditTxnQty(Number(e.target.value))} />
                      ) : (
                        t.quantity
                      )}
                    </td>
                    <td className="py-2">
                      {editingTxnId === t.id ? (
                        <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1" type="number" step="0.01" value={editTxnPrice} onChange={e => setEditTxnPrice(Number(e.target.value))} />
                      ) : (
                        t.price.toFixed(2)
                      )}
                    </td>
                    <td className="py-2">{t.total.toFixed(2)}</td>
                    <td className="py-2">{t.realized_profit.toFixed(2)}</td>
                    <td className="py-2">
                      {editingTxnId === t.id ? (
                        <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1 w-64" value={editTxnNotes} onChange={e => setEditTxnNotes(e.target.value)} />
                      ) : (
                        <span title={t.notes || ''}>{(t.notes || '').slice(0, 24)}{(t.notes || '').length > 24 ? '…' : ''}</span>
                      )}
                    </td>
                    <td className="py-2">
                      {editingTxnId === t.id ? (
                        <div className="flex gap-2">
                          <button className="px-3 py-1 bg-gray-900 text-white rounded" onClick={() => onTxnSave(t.id)}>Save</button>
                          <button className="px-3 py-1 border dark:border-gray-700 rounded" onClick={onTxnCancel}>Cancel</button>
                        </div>
                      ) : (
                        <div className="flex gap-2">
                          <button className="px-3 py-1 border dark:border-gray-700 rounded" onClick={() => onTxnEdit(t)}>Edit</button>
                          <button className="px-3 py-1 border dark:border-gray-700 rounded text-red-600" onClick={() => onTxnDelete(t.id)}>Delete</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
