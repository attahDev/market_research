const SENTIMENT_CFG = {
  positive: { label: 'Positive', color: 'var(--green-dim)', bg: 'var(--green-bg)', dot: 'var(--green)' },
  negative: { label: 'Negative', color: 'var(--red-dim)', bg: 'var(--red-bg)', dot: 'var(--red)' },
  neutral:  { label: 'Neutral',  color: 'var(--amber)',    bg: 'var(--amber-bg)', dot: 'var(--amber)' },
}

function headlineSentiment(title) {
  const t = title.toLowerCase()
  if (/surges?|jumps?|rallies|soars?|booms?|record|grows?|expands?|rises?/.test(t)) return 'positive'
  if (/falls?|drops?|slumps?|crashes?|concerns?|scrutiny|saturation|risks?/.test(t)) return 'negative'
  return 'neutral'
}

function timeAgo(dateStr) {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    const diff = Date.now() - d.getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 60) return `${mins} minutes ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs} ${hrs === 1 ? 'hour' : 'hours'} ago`
    const days = Math.floor(hrs / 24)
    return `${days} ${days === 1 ? 'day' : 'days'} ago`
  } catch { return '' }
}

export default function NewsPanel({ news }) {
  if (!news?.headlines?.length) return null

  const headlines = news.headlines.slice(0, 5)

  return (
    <div className="card" style={{ padding: '22px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
        <span style={{ fontSize: 15 }}>📰</span>
        <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>Recent News</span>
        <span style={{
          padding: '2px 8px', borderRadius: 100,
          background: 'var(--red-bg)', color: 'var(--red-dim)',
          fontSize: 10, fontWeight: 700,
        }}>Live</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        {headlines.map((h, i) => {
          const sent = headlineSentiment(h.title)
          const cfg  = SENTIMENT_CFG[sent]
          return (
            <div key={i} style={{
              display: 'flex', gap: 14, alignItems: 'flex-start',
              padding: '12px 0',
              borderBottom: i < headlines.length - 1 ? '1px solid var(--border)' : 'none',
            }}>
              {/* Number */}
              <div style={{
                width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                background: 'var(--navy)', color: 'var(--yellow)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 10, fontWeight: 700, marginTop: 1,
              }}>{i + 1}</div>

              {/* Content */}
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{
                    fontSize: 11, fontWeight: 600, color: 'var(--text-2)',
                  }}>{h.source}</span>
                  <span style={{
                    padding: '1px 7px', borderRadius: 100,
                    background: cfg.bg, color: cfg.color,
                    fontSize: 10, fontWeight: 600,
                  }}>● {cfg.label}</span>
                </div>
                <a
                  href={h.url || '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    fontSize: 13, color: 'var(--text)', lineHeight: 1.5,
                    textDecoration: 'none', display: 'block', marginBottom: 4,
                    fontWeight: 500,
                  }}
                  onMouseEnter={e => e.currentTarget.style.color = 'var(--navy)'}
                  onMouseLeave={e => e.currentTarget.style.color = 'var(--text)'}
                >{h.title}</a>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  {timeAgo(h.published_at)}{h.source ? ` · ${h.source}` : ''}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
