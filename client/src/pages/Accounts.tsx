import { FormEvent, useEffect, useState } from 'react'
import api from '../api/client'

const BROKERS = ['Zerodha', 'Upstox', 'Dhan', 'Fyers', 'IIFL', 'Definedge', 'Groww', '5Paisa', 'Shoonya', 'mStock', 'PayTM', 'Kotak Securities', 'ICICI Direct']

export default function Accounts() {
  const [accounts, setAccounts] = useState<any[]>([])
  const [name, setName] = useState('')
  const [broker, setBroker] = useState<string>('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState<string>('')
  const [editBroker, setEditBroker] = useState<string>('')

  const load = async () => {
    try {
      const res = await api.get('/accounts/')
      const rows = Array.isArray(res.data) ? res.data : []
      setAccounts(rows)
    } catch (e) {
      console.error('Failed to load accounts', e)
      setAccounts([])
    }
  }
  useEffect(() => { load() }, [])

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    await api.post('/accounts/', { name, broker: broker || null })
    setName('')
    setBroker('')
    load()
  }

  const onEdit = (a: any) => {
    setEditingId(a.id)
    setEditName(a.name)
    setEditBroker(a.broker || '')
  }

  const onCancelEdit = () => {
    setEditingId(null)
    setEditName('')
    setEditBroker('')
  }

  const onSave = async (id: number) => {
    const payload: any = {}
    if (editName !== undefined) payload.name = editName
    if (editBroker !== undefined) payload.broker = editBroker || null
    await api.patch(`/accounts/${id}`, payload)
    onCancelEdit()
    load()
  }

  const onDelete = async (id: number) => {
    const ok = window.confirm('Delete account and all its holdings and transactions?')
    if (!ok) return
    await api.delete(`/accounts/${id}`)
    load()
  }

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="font-semibold mb-3">Add Account</div>
        <form onSubmit={onSubmit} className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Name" value={name} onChange={e => setName(e.target.value)} required />
          <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" value={broker} onChange={e => setBroker(e.target.value)}>
            <option value="">Select Broker</option>
            {BROKERS.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <div className="md:col-span-2">
            <button className="bg-gray-900 text-white px-4 py-2 rounded">Create</button>
          </div>
        </form>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="font-semibold mb-3">Accounts</div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b dark:border-gray-700">
                <th className="py-2">Name</th>
                <th className="py-2">Broker</th>
                <th className="py-2">Created</th>
                <th className="py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map(a => (
                <tr key={a.id} className="border-b dark:border-gray-700 last:border-b-0">
                  <td className="py-2">
                    {editingId === a.id ? (
                      <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1" value={editName} onChange={e => setEditName(e.target.value)} />
                    ) : (
                      a.name
                    )}
                  </td>
                  <td className="py-2">
                    {editingId === a.id ? (
                      <select className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1" value={editBroker} onChange={e => setEditBroker(e.target.value)}>
                        <option value="">-</option>
                        {BROKERS.map(b => <option key={b} value={b}>{b}</option>)}
                      </select>
                    ) : (
                      a.broker || '-'
                    )}
                  </td>
                  <td className="py-2">{new Date(a.created_at).toLocaleString()}</td>
                  <td className="py-2">
                    {editingId === a.id ? (
                      <div className="flex gap-2">
                        <button type="button" className="px-3 py-1 bg-gray-900 text-white rounded" onClick={() => onSave(a.id)}>Save</button>
                        <button type="button" className="px-3 py-1 border dark:border-gray-700 rounded" onClick={onCancelEdit}>Cancel</button>
                      </div>
                    ) : (
                      <div className="flex gap-2">
                        <button type="button" className="px-3 py-1 border dark:border-gray-700 rounded" onClick={() => onEdit(a)}>Edit</button>
                        <button type="button" className="px-3 py-1 border dark:border-gray-700 rounded text-red-600" onClick={() => onDelete(a.id)}>Delete</button>
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
  )
}
