import { useEffect, useMemo, useRef } from 'react'
import { createChart, ColorType, CrosshairMode, LineStyle, CandlestickData, LineData, BusinessDay, HistogramData } from 'lightweight-charts'

export type HoldingChartData = {
  dates: string[]
  ohlc: { open: number[]; high: number[]; low: number[]; close: number[]; volume?: number[] }
  heikin?: { open: number[]; high: number[]; low: number[]; close: number[] }
  bb?: { upper: (number | null)[]; middle: (number | null)[]; lower: (number | null)[] }
  buy_price: number
  sl_price?: number
  r_levels?: (number | null)[]
  tlsl_price?: number
  tlsl_hit?: boolean
  rsi?: (number | null)[]
  sl_points?: number
  sl_pct?: number
  qty?: number
  amount_required?: number
}

export default function LWCHoldingChart({ data, useHeikin, showVolume = true, showRSI = true }: { data: HoldingChartData; useHeikin: boolean; showVolume?: boolean; showRSI?: boolean }) {
  const priceRef = useRef<HTMLDivElement | null>(null)
  const rsiRef = useRef<HTMLDivElement | null>(null)
  const prepared = useMemo(() => {
    const src = (useHeikin && data?.heikin) ? data.heikin : (data?.ohlc || { open: [], high: [], low: [], close: [], volume: [] })
    const rows: { tk: number; bd: BusinessDay; o: number; h: number; l: number; c: number; v?: number | null; u?: number | null; m?: number | null; lw?: number | null }[] = []
    const datesArr: string[] = Array.isArray(data?.dates) ? (data!.dates as string[]) : []
    for (let i = 0; i < datesArr.length; i++) {
      const d: string = datesArr[i] as string
      if (!d) continue
      const [y, m, day] = d.split('-').map((v) => Number(v))
      if (!y || !m || !day) continue
      const tk = y * 10000 + m * 100 + day
      const bd: BusinessDay = { year: y as any, month: m as any, day: day as any }
      const o = Number(src.open?.[i])
      const h = Number(src.high?.[i])
      const l = Number(src.low?.[i])
      const c = Number(src.close?.[i])
      if (!isFinite(o) || !isFinite(h) || !isFinite(l) || !isFinite(c)) continue
      const v = data.ohlc?.volume?.[i] ?? null
      rows.push({ tk, bd, o, h, l, c, v: (v == null ? null : Number(v)), u: data.bb?.upper?.[i] ?? null, m: data.bb?.middle?.[i] ?? null, lw: data.bb?.lower?.[i] ?? null })
    }
    // sort asc and dedupe by time
    rows.sort((a, b) => a.tk - b.tk)
    const deDup: typeof rows = []
    let lastT = -Infinity
    for (const r of rows) {
      if (r.tk <= lastT) continue
      deDup.push(r)
      lastT = r.tk
    }
    const candles: CandlestickData[] = deDup.map(r => ({ time: r.bd as any, open: r.o, high: r.h, low: r.l, close: r.c }))
    const upper: LineData[] = []
    const middle: LineData[] = []
    const lower: LineData[] = []
    const vols: HistogramData[] = []
    for (const r of deDup) {
      if (r.u != null) upper.push({ time: r.bd as any, value: Number(r.u) })
      if (r.m != null) middle.push({ time: r.bd as any, value: Number(r.m) })
      if (r.lw != null) lower.push({ time: r.bd as any, value: Number(r.lw) })
      if (r.v != null) {
        const up = r.c >= r.o
        vols.push({ time: r.bd as any, value: Number(r.v), color: up ? '#16a34a' : '#ef4444' })
      }
    }
    // RSI pairs
    const rsi: LineData[] = []
    const rsivals = Array.isArray(data.rsi) ? data.rsi : []
    // Build numeric RSI aligned to deDup length; fill NaN when missing
    const rsiValsAligned: number[] = []
    for (let i = 0; i < deDup.length; i++) {
      const v = rsivals[i]
      const row = deDup[i]
      if (!row) continue
      rsiValsAligned.push(typeof v === 'number' ? v : NaN)
      if (typeof v === 'number' && Number.isFinite(v)) {
        rsi.push({ time: row.bd as any, value: v })
      }
    }
    // Divergence markers (simple pivot-based)
    const markers: any[] = []
    if (rsiValsAligned.length >= 7) {
      const pivH: number[] = []
      const pivL: number[] = []
      const w = 3
      const rsiVals = rsiValsAligned
      for (let i = w; i < rsiVals.length - w; i++) {
        const v = rsiVals[i] ?? NaN
        if (!Number.isFinite(v)) continue
        let isHigh = true, isLow = true
        for (let k = 1; k <= w; k++) {
          const left = rsiVals[i-k] ?? NaN
          const right = rsiVals[i+k] ?? NaN
          if (!(Number.isFinite(left) && Number.isFinite(right))) { isHigh = false; isLow = false; break }
          if (!(v > left && v > right)) isHigh = false
          if (!(v < left && v < right)) isLow = false
        }
        if (isHigh) pivH.push(i)
        if (isLow) pivL.push(i)
      }
      // Bearish divergence
      for (let j = 1; j < pivH.length; j++) {
        const a = pivH[j-1], b = pivH[j]
        if (a == null || b == null) continue
        const priceA = deDup[a] ? (deDup[a].h ?? deDup[a].c) : NaN
        const priceB = deDup[b] ? (deDup[b].h ?? deDup[b].c) : NaN
        const rsiA = rsiVals[a] ?? NaN, rsiB = rsiVals[b] ?? NaN
        if (Number.isFinite(priceA) && Number.isFinite(priceB) && Number.isFinite(rsiA) && Number.isFinite(rsiB) && priceB > priceA && rsiB < rsiA) {
          const rowB = deDup[b]
          if (!rowB) continue
          const t = rowB.bd as any
          markers.push({ time: t, position: 'aboveBar', color: '#ef4444', shape: 'arrowDown', text: 'Bear Div' })
        }
      }
      // Bullish divergence
      for (let j = 1; j < pivL.length; j++) {
        const a = pivL[j-1], b = pivL[j]
        if (a == null || b == null) continue
        const priceA = deDup[a] ? (deDup[a].l ?? deDup[a].c) : NaN
        const priceB = deDup[b] ? (deDup[b].l ?? deDup[b].c) : NaN
        const rsiA = rsiVals[a] ?? NaN, rsiB = rsiVals[b] ?? NaN
        if (Number.isFinite(priceA) && Number.isFinite(priceB) && Number.isFinite(rsiA) && Number.isFinite(rsiB) && priceB < priceA && rsiB > rsiA) {
          const rowB = deDup[b]
          if (!rowB) continue
          const t = rowB.bd as any
          markers.push({ time: t, position: 'belowBar', color: '#10b981', shape: 'arrowUp', text: 'Bull Div' })
        }
      }
    }
    return { candles, upper, middle, lower, vols, rsi, rows: deDup, markers }
  }, [data, useHeikin])

  useEffect(() => {
    const el = priceRef.current!
    const isDark = document.documentElement.classList.contains('dark')
    const bg = isDark ? '#111827' : '#ffffff'
    const text = isDark ? '#e5e7eb' : '#111827'
    const border = isDark ? '#374151' : '#e5e7eb'
    const grid = bg
    const chart = createChart(el, {
      layout: { background: { type: ColorType.Solid, color: bg }, textColor: text },
      grid: {
        vertLines: { visible: false, color: grid },
        horzLines: { visible: false, color: grid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: border },
      leftPriceScale: { borderColor: border, visible: false },
      timeScale: { borderColor: border, timeVisible: true },
      autoSize: true,
      height: el.clientHeight || 360,
    })

    if (prepared.candles.length === 0) {
      return () => {}
    }
    const candles = chart.addCandlestickSeries({
      upColor: '#16a34a', downColor: '#ef4444', borderVisible: false,
      wickUpColor: text, wickDownColor: text,
    })
    candles.setData(prepared.candles)
    try { candles.priceScale().applyOptions({ scaleMargins: { top: 0, bottom: (showVolume && prepared.vols.length) ? 0.2 : 0 } }) } catch {}
    chart.timeScale().fitContent()

    // Price line for buy price
    candles.createPriceLine({ price: Number(data.buy_price), color: '#6b7280', lineWidth: 2, lineStyle: LineStyle.Solid, title: 'Buy' })

    // SL and R levels
    if (data.sl_price && data.sl_price > 0) {
      candles.createPriceLine({ price: Number(data.sl_price), color: '#ef4444', lineWidth: 2, lineStyle: LineStyle.Solid, title: 'SL' })
    }
    const r = Array.isArray(data.r_levels) ? data.r_levels : []
    if (r[0]) candles.createPriceLine({ price: Number(r[0]), color: '#f59e0b', lineWidth: 2, lineStyle: LineStyle.Solid, title: 'R1' })
    if (r[1]) candles.createPriceLine({ price: Number(r[1]), color: '#0ea5e9', lineWidth: 2, lineStyle: LineStyle.Solid, title: 'R2' })
    if (r[2]) candles.createPriceLine({ price: Number(r[2]), color: '#8b5cf6', lineWidth: 2, lineStyle: LineStyle.Solid, title: 'R3' })
    if (data.tlsl_price && data.tlsl_price > 0) {
      candles.createPriceLine({ price: Number(data.tlsl_price), color: '#dc2626', lineWidth: 2, lineStyle: LineStyle.Solid, title: 'TLSL' })
    }

    const sUpper = chart.addLineSeries({ color: '#2563eb', lineWidth: 1 })
    const sMiddle = chart.addLineSeries({ color: '#10b981', lineWidth: 1 })
    const sLower = chart.addLineSeries({ color: '#ef4444', lineWidth: 1 })
    sUpper.setData(prepared.upper)
    sMiddle.setData(prepared.middle)
    sLower.setData(prepared.lower)

    // Volume histogram at bottom 20%
    if (showVolume && prepared.vols.length) {
      const vol = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'left' })
      vol.setData(prepared.vols)
      try { vol.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } }) } catch {}
    }

    // Divergence markers on price candles
    try { if (prepared.markers?.length) (candles as any).setMarkers(prepared.markers) } catch {}

    // Custom OHLC tooltip overlay (top-left)
    const tip = document.createElement('div')
    tip.style.position = 'absolute'
    tip.style.left = '8px'
    tip.style.top = '8px'
    tip.style.zIndex = '10'
    tip.style.background = isDark ? 'rgba(17,24,39,0.9)' : 'rgba(255,255,255,0.9)'
    tip.style.border = `1px solid ${border}`
    tip.style.color = text
    tip.style.borderRadius = '6px'
    tip.style.padding = '6px 8px'
    tip.style.fontSize = '12px'
    tip.style.color = text
    tip.style.pointerEvents = 'none'
    el.style.position = 'relative'
    el.appendChild(tip)

    const fmt = (n: number | undefined) => (n == null ? '-' : n.toFixed(2))
    const fmtDate = (t: any) => {
      if (!t) return ''
      if (typeof t === 'number') {
        const d = new Date(t * 1000)
        return d.toISOString().slice(0, 10)
      }
      // BusinessDay
      const y = (t as any).year, m = (t as any).month, d = (t as any).day
      return `${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`
    }
    const setTip = (time: any, o?: number, h?: number, l?: number, c?: number) => {
      tip.style.display = 'block'
      const tlsl = data.tlsl_price && data.tlsl_price > 0 ? ` | TLSL: ${fmt(data.tlsl_price)}` : ''
      const slStr = (data.sl_price && data.sl_price>0) ? ` | SL: ${fmt(data.sl_price)}` : ''
      const slPts = (typeof data.sl_points === 'number' && isFinite(data.sl_points) && data.sl_points>0) ? ` | Pts: ${fmt(data.sl_points)}` : ''
      const slPct = (typeof data.sl_pct === 'number' && isFinite(data.sl_pct) && data.sl_pct>0) ? ` | SL%: ${fmt(data.sl_pct)}%` : ''
      const qty = (typeof data.qty === 'number' && data.qty>0) ? ` | Qty: ${data.qty}` : ''
      const amt = (typeof data.amount_required === 'number' && data.amount_required>0) ? ` | Amt: ${fmt(data.amount_required)}` : ''
      tip.innerHTML = `<div><strong>${fmtDate(time)}</strong></div>
        <div>O: ${fmt(o)} H: ${fmt(h)} L: ${fmt(l)} C: ${fmt(c)}</div>
        <div style="margin-top:2px">Buy: ${fmt(data.buy_price)}${slStr}${slPts}${slPct}${qty}${amt}${tlsl}</div>`
    }

    // Initialize with last candle
    const last = prepared.candles[prepared.candles.length - 1]
    if (last) setTip((last as any).time, (last as any).open, (last as any).high, (last as any).low, (last as any).close)

    const moveHandler = (param: any) => {
      if (!param || !param.time) return
      const d = param.seriesData?.get(candles)
      if (!d) return
      setTip(param.time, d.open, d.high, d.low, d.close)
    }
    chart.subscribeCrosshairMove(moveHandler)

    // Resize
    const ro = new ResizeObserver(() => {
      const { clientWidth, clientHeight } = el
      chart.applyOptions({ height: clientHeight || 360 })
      chart.timeScale().fitContent()
    })
    ro.observe(el)

    // Update on prepared changes
    return () => {
      ro.disconnect()
      chart.unsubscribeCrosshairMove(moveHandler)
      if (tip && tip.parentElement) tip.parentElement.removeChild(tip)
      chart.remove()
    }
  }, [prepared, data.buy_price, showVolume])

  // RSI sub-chart
  useEffect(() => {
    if (!showRSI) {
      const el = rsiRef.current
      if (el) el.innerHTML = ''
      return
    }
    const el = rsiRef.current!
    const isDark = document.documentElement.classList.contains('dark')
    const bg = isDark ? '#111827' : '#ffffff'
    const text = isDark ? '#e5e7eb' : '#111827'
    const border = isDark ? '#374151' : '#e5e7eb'
    const grid = bg
    const rsiChart = createChart(el, {
      layout: { background: { type: ColorType.Solid, color: bg }, textColor: text },
      grid: { vertLines: { visible: false, color: grid }, horzLines: { visible: false, color: grid } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: border },
      timeScale: { borderColor: border, timeVisible: true },
    })
    if (!prepared.rsi.length) return () => { rsiChart.remove() }
    const s = rsiChart.addLineSeries({ color: '#6b7280', lineWidth: 1 })
    s.setData(prepared.rsi)
    s.createPriceLine({ price: 70, color: '#ef4444', lineWidth: 1, lineStyle: LineStyle.Solid, title: '70' })
    s.createPriceLine({ price: 50, color: '#9ca3af', lineWidth: 1, lineStyle: LineStyle.Solid, title: '50' })
    s.createPriceLine({ price: 30, color: '#10b981', lineWidth: 1, lineStyle: LineStyle.Solid, title: '30' })
    rsiChart.timeScale().fitContent()

    const ro = new ResizeObserver(() => {
      const { clientHeight } = el
      rsiChart.applyOptions({ height: clientHeight || 160 })
      rsiChart.timeScale().fitContent()
    })
    ro.observe(el)
    return () => { ro.disconnect(); rsiChart.remove() }
  }, [prepared, showRSI])

  return (
    <div className="w-full">
      <div ref={priceRef} className="h-96 w-full" />
      {showRSI && <div ref={rsiRef} className="h-40 w-full mt-2" />}
    </div>
  )
}
