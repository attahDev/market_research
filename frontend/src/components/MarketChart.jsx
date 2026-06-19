import { useState, useRef, useEffect, useCallback } from 'react'

const PERIODS = ['1d', '7d', '30d', '1y', '5y']

function pickData(chartData, period) {
  const map = {
    '1d':  chartData?.ohlc_1d,
    '7d':  chartData?.ohlc_7d,
    '30d': chartData?.ohlc_30d,
    '1y':  chartData?.ohlc_1y,
    '5y':  chartData?.ohlc_5y,
  }
  return (map[period] || []).filter(Boolean)
}

function fmtLabel(time, period) {
  const d = new Date(time)
  if (period === '1d') return d.toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' })
  if (period === '7d') return d.toLocaleDateString('en', { weekday: 'short', month: 'short', day: 'numeric' })
  if (period === '30d') return d.toLocaleDateString('en', { month: 'short', day: 'numeric' })
  return d.toLocaleDateString('en', { month: 'short', year: '2-digit' })
}

function fmtPrice(p) {
  if (p == null) return '—'
  if (p >= 1000) return `$${p.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
  if (p >= 1)    return `$${p.toFixed(2)}`
  return `$${p.toFixed(6)}`
}

export default function MarketChart({ chartData, category }) {
  const [period, setPeriod]   = useState('7d')
  const [tooltip, setTooltip] = useState(null) // { x, y, price, time, pct }
  const canvasRef = useRef(null)
  const coordsRef = useRef([]) // store [{x, price, time}] for hover lookup

  const data = pickData(chartData, period)

  const draw = useCallback(() => {
    if (!data.length) return
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width  = rect.width  * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)
    const W = rect.width
    const H = rect.height

    ctx.clearRect(0, 0, W, H)

    const prices = data.map(d => d.close || d.open || 0)
    const min    = Math.min(...prices)
    const max    = Math.max(...prices)
    const range  = max - min || 1

    const pad = { top: 12, right: 12, bottom: 32, left: 56 }
    const w   = W - pad.left - pad.right
    const h   = H - pad.top  - pad.bottom

    const isPos      = prices[prices.length - 1] >= prices[0]
    const lineColor  = isPos ? '#22c55e' : '#ef4444'
    const fillColor  = isPos ? 'rgba(34,197,94,0.10)' : 'rgba(239,68,68,0.10)'
    const gridColor  = '#e2e6ea'

    const toX = (i) => pad.left + (i / (prices.length - 1 || 1)) * w
    const toY = (p) => pad.top  + ((max - p) / range) * h
    ctx.setLineDash([3, 4])
    ctx.strokeStyle = gridColor
    ctx.lineWidth   = 1
    for (let i = 0; i <= 4; i++) {
      const y   = pad.top + (h * i) / 4
      const val = max - (range * i) / 4
      ctx.beginPath()
      ctx.moveTo(pad.left, y)
      ctx.lineTo(pad.left + w, y)
      ctx.stroke()
      ctx.setLineDash([])
      ctx.fillStyle   = '#8896a7'
      ctx.font        = `10px Inter, sans-serif`
      ctx.textAlign   = 'right'
      ctx.fillText(fmtPrice(val), pad.left - 4, y + 4)
    }
    ctx.setLineDash([])
    const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + h)
    grad.addColorStop(0, isPos ? 'rgba(34,197,94,0.18)' : 'rgba(239,68,68,0.18)')
    grad.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.beginPath()
    ctx.moveTo(toX(0), toY(prices[0]))
    for (let i = 1; i < prices.length; i++) ctx.lineTo(toX(i), toY(prices[i]))
    ctx.lineTo(toX(prices.length - 1), pad.top + h)
    ctx.lineTo(toX(0), pad.top + h)
    ctx.closePath()
    ctx.fillStyle = grad
    ctx.fill()

    ctx.beginPath()
    ctx.moveTo(toX(0), toY(prices[0]))
    for (let i = 1; i < prices.length; i++) ctx.lineTo(toX(i), toY(prices[i]))
    ctx.strokeStyle = lineColor
    ctx.lineWidth   = 2
    ctx.stroke()

    const lx = toX(prices.length - 1)
    const ly = toY(prices[prices.length - 1])
    ctx.beginPath()
    ctx.arc(lx, ly, 4, 0, Math.PI * 2)
    ctx.fillStyle = lineColor
    ctx.fill()

    const steps = Math.min(5, data.length - 1)
    ctx.fillStyle  = '#8896a7'
    ctx.font       = '10px Inter, sans-serif'
    ctx.textAlign  = 'center'
    for (let i = 0; i <= steps; i++) {
      const idx = Math.round((i / steps) * (data.length - 1))
      const d   = data[idx]
      if (!d?.time) continue
      ctx.fillText(fmtLabel(d.time, period), toX(idx), pad.top + h + 20)
    }
    coordsRef.current = prices.map((p, i) => ({
      x:     toX(i),
      y:     toY(p),
      price: p,
      time:  data[i]?.time,
    }))
  }, [data, period])

  useEffect(() => {
    draw()
  }, [draw])

  const handleMouseMove = useCallback((e) => {
    const canvas = canvasRef.current
    if (!canvas || !coordsRef.current.length) return
    const rect   = canvas.getBoundingClientRect()
    const mouseX = e.clientX - rect.left
    let nearest = null
    let minDist = Infinity
    for (const pt of coordsRef.current) {
      const d = Math.abs(pt.x - mouseX)
      if (d < minDist) { minDist = d; nearest = pt }
    }

    if (!nearest || minDist > 40) { setTooltip(null); return }

    const prices  = coordsRef.current.map(p => p.price)
    const first   = prices[0]
    const pct     = first ? ((nearest.price - first) / first * 100) : 0
    const isPos   = pct >= 0

    const tipW   = 130
    const tipX   = nearest.x + rect.left + (nearest.x > rect.width - tipW - 20 ? -(tipW + 12) : 12)
    const tipY   = nearest.y + rect.top - 10

    setTooltip({
      x:    tipX,
      y:    tipY,
      canvasX: nearest.x,
      canvasY: nearest.y,
      price:   nearest.price,
      time:    nearest.time,
      pct,
      isPos,
    })
  }, [period])

  const handleMouseLeave = useCallback(() => setTooltip(null), [])

  const overlayRef = useRef(null)
  useEffect(() => {
    const overlay = overlayRef.current
    if (!overlay) return
    const ctx = overlay.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const rect = overlay.getBoundingClientRect()
    overlay.width  = rect.width  * dpr
    overlay.height = rect.height * dpr
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, rect.width, rect.height)

    if (!tooltip) return
    const canvas = canvasRef.current
    if (!canvas) return
    const cRect = canvas.getBoundingClientRect()

    ctx.setLineDash([4, 4])
    ctx.strokeStyle = '#8896a7'
    ctx.lineWidth   = 1

    ctx.beginPath()
    ctx.moveTo(tooltip.canvasX, 12)
    ctx.lineTo(tooltip.canvasX, cRect.height - 32)
    ctx.stroke()
    ctx.setLineDash([])
    ctx.beginPath()
    ctx.arc(tooltip.canvasX, tooltip.canvasY, 5, 0, Math.PI * 2)
    ctx.fillStyle   = tooltip.isPos ? '#22c55e' : '#ef4444'
    ctx.fill()
    ctx.strokeStyle = '#fff'
    ctx.lineWidth   = 2
    ctx.stroke()
  }, [tooltip])

  if (!chartData) return null

  const prices    = data.map(d => d.close || 0)
  const pctChange = prices.length > 1 && prices[0]
    ? ((prices[prices.length - 1] - prices[0]) / prices[0] * 100)
    : 0
  const isPos = pctChange >= 0

  return (
    <div className="card" style={{ padding: '18px 20px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 14 }}>📈</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: '#0d1b2e' }}>Market Growth Trend</span>
        </div>
        {data.length > 0 && (
          <span style={{ fontSize: 12, fontWeight: 600, color: isPos ? '#16a34a' : '#dc2626' }}>
            {isPos ? '+' : ''}{pctChange.toFixed(2)}%
          </span>
        )}
      </div>

      {/* Period tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
        {PERIODS.map(p => (
          <button key={p} onClick={() => { setPeriod(p); setTooltip(null) }} style={{
            padding: '3px 9px', borderRadius: 6, fontSize: 11, fontWeight: 600,
            border: 'none', cursor: 'pointer',
            background: period === p ? '#0d1b2e' : 'transparent',
            color:      period === p ? '#f5c518' : '#8896a7',
            transition: 'all 0.12s',
          }}>{p.toUpperCase()}</button>
        ))}
      </div>

      {data.length > 0 ? (
        <div style={{ position: 'relative', height: 168 }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} />
          <canvas ref={overlayRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }} />

          {/* Tooltip */}
          {tooltip && (
            <div style={{
              position: 'fixed',
              left: tooltip.x,
              top:  tooltip.y,
              background: '#0d1b2e',
              color: '#fff',
              borderRadius: 8,
              padding: '8px 12px',
              fontSize: 12,
              pointerEvents: 'none',
              zIndex: 100,
              boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
              minWidth: 120,
            }}>
              <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 2 }}>
                {fmtPrice(tooltip.price)}
              </div>
              <div style={{ color: tooltip.isPos ? '#4ade80' : '#f87171', fontSize: 11, marginBottom: 4 }}>
                {tooltip.isPos ? '+' : ''}{tooltip.pct.toFixed(2)}%
              </div>
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 10 }}>
                {tooltip.time ? fmtLabel(tooltip.time, period) : ''}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div style={{
          height: 168, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#8896a7', fontSize: 13,
        }}>
          No chart data for this period
        </div>
      )}
    </div>
  )
}
