import { useMemo } from 'react'
import { ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine, Legend, Bar, Cell } from 'recharts'

export type HoldingChartData = {
  dates: string[]
  ohlc: { open: number[]; high: number[]; low: number[]; close: number[] }
  heikin?: { open: number[]; high: number[]; low: number[]; close: number[] }
  bb?: { upper: (number | null)[]; middle: (number | null)[]; lower: (number | null)[] }
  buy_price: number
}

export default function HoldingChart({ data, useHeikin }: { data: HoldingChartData; useHeikin: boolean }) {
  const rows = useMemo(() => {
    const len = data?.dates?.length || 0
    const src = useHeikin && data.heikin ? data.heikin : data.ohlc
    const bb = data.bb
    const out: any[] = []
    for (let i = 0; i < len; i++) {
      const open = Number(src.open?.[i])
      const close = Number(src.close?.[i])
      const high = Number(src.high?.[i])
      const low = Number(src.low?.[i])
      if (!isFinite(open) || !isFinite(close) || !isFinite(high) || !isFinite(low)) continue
      const bodyBottom = Math.min(open, close)
      const bodyHeight = Math.max(open, close) - bodyBottom
      const wickBottom = low
      const wickHeight = high - low
      out.push({
        date: data.dates[i],
        open, close, high, low,
        bodyBottom, bodyHeight,
        wickBottom, wickHeight,
        isUp: close >= open,
        upper: bb?.upper?.[i] ?? null,
        middle: bb?.middle?.[i] ?? null,
        lower: bb?.lower?.[i] ?? null,
      })
    }
    return out
  }, [data, useHeikin])

  return (
    <div className="h-96">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" minTickGap={24} tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} domain={[(dataMin: number) => Math.floor(dataMin * 0.95), (dataMax: number) => Math.ceil(dataMax * 1.05)]} />
          <Tooltip />
          <Legend />
          <ReferenceLine y={data.buy_price} stroke="#6b7280" strokeDasharray="4 4" label={{ value: 'Buy', position: 'insideTopRight', fill: '#6b7280' }} />

          {/* Wick: very thin stacked bars to draw from low to high */}
          <Bar dataKey="wickBottom" stackId="wick" fill="transparent" barSize={1} isAnimationActive={false} />
          <Bar dataKey="wickHeight" stackId="wick" fill="#111827" barSize={1} isAnimationActive={false} />

          {/* Body: stacked bars where the bottom offsets to min(open, close), height is abs diff */}
          <Bar dataKey="bodyBottom" stackId="body" fill="transparent" barSize={6} isAnimationActive={false} />
          <Bar dataKey="bodyHeight" stackId="body" barSize={6} isAnimationActive={false}>
            {rows.map((r, i) => (
              <Cell key={`c-${i}`} fill={r.isUp ? '#16a34a' : '#ef4444'} />
            ))}
          </Bar>

          {/* Close overlay line */}
          <Line type="monotone" dataKey="close" stroke="#111827" strokeWidth={1.5} dot={false} name={useHeikin ? 'HA Close' : 'Close'} />

          {/* Bollinger bands */}
          <Line type="monotone" dataKey="upper" stroke="#2563eb" strokeWidth={1} dot={false} name="BB Upper" />
          <Line type="monotone" dataKey="middle" stroke="#10b981" strokeWidth={1} dot={false} name="BB Middle" />
          <Line type="monotone" dataKey="lower" stroke="#ef4444" strokeWidth={1} dot={false} name="BB Lower" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
