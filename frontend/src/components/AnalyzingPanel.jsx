const STEPS = [
  'Searching live market databases',
  'Gathering recent news & trends',
  'Analysing competitor landscape',
  'Generating insights & opportunities',
]

function resolveLevel(status) {
  switch (status) {
    case 'pending':    return 0
    case 'processing': return 2
    case 'complete':   return 4
    default:           return 1
  }
}

export default function AnalyzingPanel({ query, status, onCancel }) {
  const level = resolveLevel(status)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* ── Main analysing card ── */}
      <div className="card fade-up" style={{ padding: '26px 30px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 22 }}>

          {/* Spinner */}
          <div style={{ flexShrink: 0, paddingTop: 2 }}>
            <div style={{
              width: 38, height: 38,
              border: '3px solid rgba(245,197,24,0.2)',
              borderTopColor: '#f5c518',
              borderRadius: '50%',
              animation: 'spin 0.85s linear infinite',
            }} />
          </div>

          {/* Steps */}
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 15, fontWeight: 600, color: '#0d1b2e', marginBottom: 16 }}>
              Analysing:{' '}
              <span style={{ fontStyle: 'italic', color: '#4a5568' }}>"{query}"</span>...
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {STEPS.map((step, i) => {
                const done   = i < level - 1
                const active = i === level - 1
                const pend   = !done && !active
                return (
                  <div key={step} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{
                      width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                      background: done ? '#22c55e' : active ? '#f5c518' : '#e2e6ea',
                      animation: active ? 'pulse-dot 1.2s ease infinite' : 'none',
                    }} />
                    <span style={{
                      fontSize: 13.5,
                      color:  done ? '#16a34a' : active ? '#0d1b2e' : '#8896a7',
                      fontWeight: active ? 600 : 400,
                    }}>{step}</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Cancel */}
          <button
            onClick={onCancel}
            style={{
              flexShrink: 0, padding: '6px 14px',
              border: '1px solid #e2e6ea', borderRadius: 8,
              background: 'transparent', color: '#4a5568',
              fontSize: 12, cursor: 'pointer',
              fontFamily: 'Inter, sans-serif', fontWeight: 500,
            }}
          >Cancel</button>
        </div>
      </div>

      {/* ── Skeleton grid ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        {[1, 2, 3].map(n => (
          <div key={n} className="card" style={{ padding: 20 }}>
            <div className="skeleton" style={{ height: 13, width: '50%', marginBottom: 12 }} />
            <div className="skeleton" style={{ height: 9, width: '80%', marginBottom: 7 }} />
            <div className="skeleton" style={{ height: 9, width: '60%' }} />
          </div>
        ))}
      </div>

      {/* ── Skeleton wide ── */}
      <div className="card" style={{ padding: 24 }}>
        <div className="skeleton" style={{ height: 13, width: '35%', marginBottom: 16 }} />
        <div className="skeleton" style={{ height: 9, width: '100%', marginBottom: 9 }} />
        <div className="skeleton" style={{ height: 9, width: '88%', marginBottom: 9 }} />
        <div className="skeleton" style={{ height: 9, width: '70%' }} />
      </div>

      {/* ── Skeleton 2-col ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {[1, 2].map(n => (
          <div key={n} className="card" style={{ padding: 22 }}>
            <div className="skeleton" style={{ height: 13, width: '40%', marginBottom: 14 }} />
            <div className="skeleton" style={{ height: 9, width: '90%', marginBottom: 8 }} />
            <div className="skeleton" style={{ height: 9, width: '75%', marginBottom: 8 }} />
            <div className="skeleton" style={{ height: 9, width: '80%' }} />
          </div>
        ))}
      </div>
    </div>
  )
}
