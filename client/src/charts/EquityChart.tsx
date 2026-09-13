import { useMemo } from 'react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts'

export default function EquityChart({ data }: { data: { date: string; portfolio_value: number; realized: number; unrealized: number }[] }) {
  const isDark = useMemo(() => document.documentElement.classList.contains('dark'), [])
  const tooltipStyle = useMemo(() => {
    return {
      backgroundColor: isDark ? 'rgba(17,24,39,0.95)' : 'rgba(255,255,255,0.95)',
      border: isDark ? '1px solid #374151' : '1px solid #e5e7eb',
      color: isDark ? '#e5e7eb' : '#111827',
      fontSize: '12px',
      borderRadius: '8px',
      padding: '8px 10px',
    } as const
  }, [isDark])

  const labelStyle = useMemo(() => {
    return {
      color: isDark ? '#93c5fd' : '#1d4ed8',
      fontWeight: 600,
    } as const
  }, [isDark])

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 h-80">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
          <XAxis dataKey="date" minTickGap={24} tick={{ fontSize: 12 }} />
          <YAxis yAxisId="left" tick={{ fontSize: 12 }} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} />
          <Tooltip contentStyle={tooltipStyle} labelStyle={labelStyle} />
          <Legend />
          <Line yAxisId="left" type="monotone" dataKey="portfolio_value" name="Portfolio Value" stroke="#2563eb" strokeWidth={2} dot={false} />
          <Line yAxisId="right" type="monotone" dataKey="unrealized" name="Unrealized P/L" stroke="#16a34a" strokeWidth={2} dot={false} />
          <Line yAxisId="right" type="monotone" dataKey="realized" name="Realized P/L" stroke="#f97316" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
