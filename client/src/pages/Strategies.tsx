import { FormEvent, useEffect, useState } from 'react'
import api from '../api/client'

export default function Strategies() {
  const [strategies, setStrategies] = useState<any[]>([])
  const [name, setName] = useState<string>('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState<string>('')

  const load = async () => {
    try {
      const res = await api.get('/strategies/')
      setStrategies(Array.isArray(res.data) ? res.data : [])
    } catch (e) {
      console.error('Failed to load strategies', e)
      setStrategies([])
    }
  }

  useEffect(() => { void load() }, [])

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    await api.post('/strategies/', { name })
    setName('')
    await load()
  }

  const onEdit = (s: any) => {
    setEditingId(s.id)
    setEditName(s.name || '')
  }

  const onCancel = () => {
    setEditingId(null)
    setEditName('')
  }

  const onSave = async (id: number) => {
    await api.patch(`/strategies/${id}`, { name: editName })
    onCancel()
    await load()
  }

  const onDelete = async (id: number) => {
    const ok = window.confirm('Delete strategy? Transactions will be moved to Swing.')
    if (!ok) return
    await api.delete(`/strategies/${id}`)
    await load()
  }

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="font-semibold mb-3">Add Strategy</div>
        <form onSubmit={onSubmit} className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-3 py-2" placeholder="Name" value={name} onChange={e => setName(e.target.value)} required />
          <div className="md:col-span-3">
            <button className="bg-gray-900 text-white px-4 py-2 rounded">Create</button>
          </div>
        </form>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
        <div className="font-semibold mb-3">Strategies</div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b dark:border-gray-700">
                <th className="py-2">Name</th>
                <th className="py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((s) => (
                <tr key={s.id} className="border-b dark:border-gray-700 last:border-b-0">
                  <td className="py-2">
                    {editingId === s.id ? (
                      <input className="border dark:border-gray-700 dark:bg-gray-900 rounded px-2 py-1" value={editName} onChange={e => setEditName(e.target.value)} />
                    ) : (
                      <span className={s.name === 'Swing' ? 'font-semibold' : ''}>{s.name}</span>
                    )}
                  </td>
                  <td className="py-2">
                    {editingId === s.id ? (
                      <div className="flex gap-2">
                        <button type="button" className="px-3 py-1 bg-gray-900 text-white rounded" onClick={() => onSave(s.id)}>Save</button>
                        <button type="button" className="px-3 py-1 border dark:border-gray-700 rounded" onClick={onCancel}>Cancel</button>
                      </div>
                    ) : (
                      <div className="flex gap-2">
                        <button type="button" className="px-3 py-1 border dark:border-gray-700 rounded" onClick={() => onEdit(s)}>Edit</button>
                        <button type="button" className="px-3 py-1 border dark:border-gray-700 rounded text-red-600 disabled:opacity-50" disabled={s.name === 'Swing'} onClick={() => onDelete(s.id)}>Delete</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {strategies.length === 0 && (
                <tr><td colSpan={2} className="text-center py-6 text-gray-500">No strategies</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
