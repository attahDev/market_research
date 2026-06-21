import { useState, useEffect } from 'react'

const CHIPS = [
  { emoji: '🌿', label: 'Sustainable Fashion Africa' },
  { emoji: '⚡', label: 'EV Market Nigeria' },
  { emoji: '🏦', label: 'Fintech West Africa' },
  { emoji: '🤖', label: 'AI SaaS Trends' },
  { emoji: '🎓', label: 'EdTech Growth' },
]

export default function HeroSearch({ onSubmit, defaultQuery = '', disabled }) {
  const [query, setQuery] = useState(defaultQuery)
  useEffect(() => { setQuery(defaultQuery) }, [defaultQuery])
  const go = (q) => { const v = (q || query).trim(); if (!v || disabled) return; onSubmit(v) }

  return (
    <div className="hero-pad" style={{
      background: '#0d1b2e', borderRadius: 16,
      padding: '34px 40px 30px', position: 'relative', overflow: 'hidden',
    }}>
      <div className="hero-pattern" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} />
      <div style={{
        position: 'absolute', right: -40, top: -40, width: 260, height: 260,
        background: 'radial-gradient(circle, rgba(245,197,24,0.07) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Badge */}
      <div style={{ marginBottom: 14, position: 'relative' }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '4px 12px', borderRadius: 100,
          background: 'rgba(245,197,24,0.15)', border: '1px solid rgba(245,197,24,0.3)',
          fontSize: 11, fontWeight: 500, color: '#f5c518',
        }}>✦ AI-Powered · Real-Time Data</span>
      </div>

      {/* Heading */}
      <h1 className="hero-heading" style={{
        fontSize: 28, fontWeight: 800, marginBottom: 8, color: '#fff',
        letterSpacing: '-0.015em', position: 'relative',
      }}>
        AI <span style={{ color: '#f5c518' }}>Market Research</span>
      </h1>
      <p className="hero-sub" style={{
        fontSize: 13.5, color: 'rgba(255,255,255,0.58)',
        marginBottom: 24, position: 'relative', lineHeight: 1.55,
      }}>
        Discover insights, trends, and opportunities powered by AI.
      </p>

      {/* Search bar */}
      <div className="hero-search-bar" style={{
        display: 'flex', alignItems: 'center',
        background: 'rgba(255,255,255,0.97)',
        borderRadius: 100, padding: '6px 6px 6px 20px',
        position: 'relative', zIndex: 2,
        boxShadow: '0 6px 28px rgba(0,0,0,0.25)',
      }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#8896a7" strokeWidth="2"
          style={{ flexShrink: 0, marginRight: 10 }}>
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && go()}
          disabled={disabled}
          placeholder="Search market, industry, or opportunity..."
          style={{
            flex: 1, border: 'none', outline: 'none', minWidth: 0,
            fontSize: 14, color: '#0d1b2e', background: 'transparent',
            fontFamily: 'Inter, sans-serif',
          }}
        />
        <button
          onClick={() => go()}
          disabled={disabled || !query.trim()}
          className="hero-btn"
          style={{
            padding: '10px 26px', borderRadius: 100,
            background: '#f5c518', color: '#0d1b2e',
            border: 'none', fontWeight: 700, fontSize: 14,
            cursor: disabled || !query.trim() ? 'not-allowed' : 'pointer',
            opacity: disabled ? 0.5 : 1,
            fontFamily: 'Inter, sans-serif',
            display: 'flex', alignItems: 'center', gap: 6,
            flexShrink: 0, whiteSpace: 'nowrap',
          }}
        >Analyze →</button>
      </div>

      {/* Quick-try chips — hidden on mobile via CSS */}
      <div className="chips-row" style={{
        display: 'flex', alignItems: 'center', gap: 8,
        marginTop: 16, flexWrap: 'wrap', position: 'relative', zIndex: 2,
      }}>
        <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.38)', marginRight: 2 }}>Try</span>
        {CHIPS.map(chip => (
          <button
            key={chip.label} disabled={disabled}
            onClick={() => go(chip.label)}
            className="chip" style={{ opacity: disabled ? 0.5 : 1 }}
          >
            <span style={{ fontSize: 11 }}>{chip.emoji}</span>
            {chip.label}
          </button>
        ))}
      </div>
    </div>
  )
}
