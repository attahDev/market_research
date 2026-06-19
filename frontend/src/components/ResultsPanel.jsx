import NewsPanel from './NewsPanel'
import MarketChart from './MarketChart'

function fmtPrice(p) {
  if (p == null) return '—'
  if (p >= 1000) return `$${p.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
  if (p >= 1)    return `$${p.toFixed(2)}`
  return `$${p.toFixed(6)}`
}

function fmt(num, { prefix = '', decimals = 2, compact = false } = {}) {
  if (num == null) return '—'
  if (compact) {
    if (Math.abs(num) >= 1e12) return `${prefix}${(num / 1e12).toFixed(decimals)}T`
    if (Math.abs(num) >= 1e9)  return `${prefix}${(num / 1e9).toFixed(decimals)}B`
    if (Math.abs(num) >= 1e6)  return `${prefix}${(num / 1e6).toFixed(decimals)}M`
    if (Math.abs(num) >= 1e3)  return `${prefix}${(num / 1e3).toFixed(decimals)}K`
  }
  return `${prefix}${num.toFixed(decimals)}`
}

function ConfidenceBadge({ dataConfidence, classifierConfidence, fetchedAt }) {
  const score = dataConfidence ?? classifierConfidence ?? null
  if (score === null) return null

  const tier =
    score >= 0.75 ? { label: 'High Confidence',   color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0', dot: '#22c55e' } :
    score >= 0.45 ? { label: 'Medium Confidence',  color: '#b45309', bg: '#fffbeb', border: '#fde68a', dot: '#f59e0b' } :
                   { label: 'Low Confidence',    color: '#dc2626', bg: '#fef2f2', border: '#fecaca', dot: '#ef4444' }

  const pct    = Math.round(score * 100)
  const barW   = `${pct}%`

  let timeStr = ''
  if (fetchedAt) {
    try {
      const d    = new Date(fetchedAt)
      const diff = Math.floor((Date.now() - d.getTime()) / 60000)
      timeStr    = diff < 1 ? 'just now' : diff < 60 ? `${diff}m ago` : `${Math.floor(diff / 60)}h ago`
    } catch {}
  }

  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      padding: '5px 12px 5px 8px',
      background: tier.bg,
      border: `1px solid ${tier.border}`,
      borderRadius: 100,
      fontSize: 11, fontWeight: 600,
    }}>
      {/* Animated dot */}
      <div style={{
        width: 7, height: 7, borderRadius: '50%',
        background: tier.dot,
        flexShrink: 0,
        animation: score < 0.45 ? 'none' : 'pulse-dot 2s ease infinite',
      }} />

      {/* Label + score */}
      <span style={{ color: tier.color }}>{tier.label}</span>
      <span style={{ color: tier.color, opacity: 0.7 }}>{pct}%</span>

      {/* Mini progress bar */}
      <div style={{
        width: 40, height: 4, borderRadius: 2,
        background: 'rgba(0,0,0,0.08)',
        overflow: 'hidden', flexShrink: 0,
      }}>
        <div style={{
          width: barW, height: '100%',
          background: tier.dot, borderRadius: 2,
          transition: 'width 0.6s ease',
        }} />
      </div>

      {/* Timestamp */}
      {timeStr && (
        <span style={{ color: tier.color, opacity: 0.55, fontWeight: 400 }}>
          · Data {timeStr}
        </span>
      )}
    </div>
  )
}

function AnalystPanel({ analyst }) {
  if (!analyst) return null
  const { buy_count, hold_count, sell_count, total_analysts,
          consensus_rating, target_price_consensus,
          target_price_high, target_price_low,
          recent_upgrades, recent_downgrades } = analyst

  const total = total_analysts || (buy_count + hold_count + sell_count) || 0
  if (!total && !consensus_rating) return null

  const buyPct  = total ? Math.round((buy_count  || 0) / total * 100) : 0
  const holdPct = total ? Math.round((hold_count || 0) / total * 100) : 0
  const sellPct = total ? Math.round((sell_count || 0) / total * 100) : 0

  const consensusColor =
    consensus_rating?.toLowerCase().includes('buy')  ? '#16a34a' :
    consensus_rating?.toLowerCase().includes('sell') ? '#dc2626' : '#b45309'

  return (
    <div className="card" style={{ padding: '22px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 15 }}>🎯</span>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#0d1b2e' }}>Analyst Ratings</span>
          {total > 0 && (
            <span style={{
              fontSize: 11, color: '#8896a7', fontWeight: 500,
              background: '#f7f8fa', border: '1px solid #e2e6ea',
              padding: '2px 8px', borderRadius: 100,
            }}>{total} analysts</span>
          )}
        </div>
        {consensus_rating && (
          <span style={{
            padding: '4px 14px', borderRadius: 100,
            background: consensusColor + '15',
            border: `1.5px solid ${consensusColor}40`,
            fontSize: 12, fontWeight: 700, color: consensusColor,
            letterSpacing: '0.04em',
          }}>{consensus_rating.toUpperCase()}</span>
        )}
      </div>

      {/* Buy / Hold / Sell bars */}
      {total > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 18 }}>
          {[
            { label: 'Buy',  count: buy_count  || 0, pct: buyPct,  color: '#22c55e', bg: '#f0fdf4' },
            { label: 'Hold', count: hold_count || 0, pct: holdPct, color: '#f59e0b', bg: '#fffbeb' },
            { label: 'Sell', count: sell_count || 0, pct: sellPct, color: '#ef4444', bg: '#fef2f2' },
          ].map(({ label, count, pct, color, bg }) => (
            <div key={label}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: '#4a5568' }}>{label}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color }}>
                  {count} <span style={{ fontWeight: 400, color: '#8896a7' }}>({pct}%)</span>
                </span>
              </div>
              <div style={{
                height: 7, borderRadius: 4, background: '#f0f2f5', overflow: 'hidden',
              }}>
                <div style={{
                  width: `${pct}%`, height: '100%',
                  background: color, borderRadius: 4,
                  transition: 'width 0.8s ease',
                }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Price target */}
      {target_price_consensus != null && (
        <div style={{
          background: '#f7f8fa', borderRadius: 10,
          padding: '14px 16px', marginBottom: 12,
        }}>
          <div style={{ fontSize: 11, color: '#8896a7', marginBottom: 6 }}>Price Target</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontSize: 20, fontWeight: 800, color: '#0d1b2e' }}>
              {fmtPrice(target_price_consensus)}
            </span>
            {target_price_low != null && target_price_high != null && (
              <span style={{ fontSize: 12, color: '#8896a7' }}>
                Range: {fmtPrice(target_price_low)} – {fmtPrice(target_price_high)}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Recent changes */}
      {(recent_upgrades != null || recent_downgrades != null) && (
        <div style={{ display: 'flex', gap: 10 }}>
          {recent_upgrades != null && (
            <div style={{
              flex: 1, background: '#f0fdf4', border: '1px solid #bbf7d0',
              borderRadius: 8, padding: '10px 12px', textAlign: 'center',
            }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: '#16a34a' }}>
                +{recent_upgrades}
              </div>
              <div style={{ fontSize: 11, color: '#16a34a' }}>Upgrades</div>
            </div>
          )}
          {recent_downgrades != null && (
            <div style={{
              flex: 1, background: '#fef2f2', border: '1px solid #fecaca',
              borderRadius: 8, padding: '10px 12px', textAlign: 'center',
            }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: '#dc2626' }}>
                -{recent_downgrades}
              </div>
              <div style={{ fontSize: 11, color: '#dc2626' }}>Downgrades</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const ACTION_CFG = {
  BUY:   { color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0', icon: '↑' },
  SELL:  { color: '#dc2626', bg: '#fef2f2', border: '#fecaca', icon: '↓' },
  HOLD:  { color: '#b45309', bg: '#fffbeb', border: '#fde68a', icon: '—' },
  WATCH: { color: '#6366f1', bg: '#eef2ff', border: '#c7d2fe', icon: '◎' },
}

const RISK_CFG = {
  Low:    { color: '#16a34a', bg: '#f0fdf4' },
  Medium: { color: '#b45309', bg: '#fffbeb' },
  High:   { color: '#dc2626', bg: '#fef2f2' },
}

function FinalRecommendationsPanel({ recommendations }) {
  if (!recommendations?.length) return null

  return (
    <div className="card fade-up" style={{ padding: '24px 26px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 16 }}>🏁</span>
        <span style={{ fontSize: 15, fontWeight: 700, color: '#0d1b2e' }}>Final Recommendations</span>
      </div>
      <p style={{ fontSize: 12, color: '#8896a7', marginBottom: 20 }}>
        AI-generated guidance based on current data · Not financial advice
      </p>

      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${Math.min(recommendations.length, 2)}, 1fr)`,
        gap: 14,
      }}>
        {recommendations.map((rec, i) => {
          const action = rec.action?.toUpperCase() || 'WATCH'
          const risk   = rec.risk_level || 'Medium'
          const aCfg   = ACTION_CFG[action] || ACTION_CFG.WATCH
          const rCfg   = RISK_CFG[risk]     || RISK_CFG.Medium

          return (
            <div key={i} style={{
              border: `1.5px solid ${aCfg.border}`,
              borderRadius: 12,
              background: aCfg.bg,
              padding: '18px 20px',
            }}>
              {/* Action badge */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '5px 14px', borderRadius: 100,
                  background: aCfg.color, color: '#fff',
                  fontSize: 13, fontWeight: 800, letterSpacing: '0.06em',
                }}>
                  <span>{aCfg.icon}</span>
                  {action}
                </div>
                <span style={{
                  padding: '3px 10px', borderRadius: 100,
                  background: rCfg.bg,
                  border: `1px solid ${rCfg.color}30`,
                  fontSize: 10, fontWeight: 600, color: rCfg.color,
                }}>
                  {risk} Risk
                </span>
              </div>

              {/* Rationale */}
              <p style={{ fontSize: 13, color: '#0d1b2e', lineHeight: 1.65, marginBottom: 10 }}>
                {rec.rationale}
              </p>

              {/* Timeframe */}
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                fontSize: 11, color: '#4a5568', fontWeight: 500,
              }}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <polyline points="12 6 12 12 16 14"/>
                </svg>
                {rec.timeframe}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}


function MetricCard({ icon, label, value, badge, badgePositive }) {
  return (
    <div className="card" style={{ padding: '20px 22px' }}>
      <div style={{ fontSize: 24, marginBottom: 10 }}>{icon}</div>
      <div style={{
        fontSize: 24, fontWeight: 800, color: '#0d1b2e',
        marginBottom: 3, letterSpacing: '-0.02em', lineHeight: 1,
      }}>{value}</div>
      <div style={{ fontSize: 11.5, color: '#8896a7', marginBottom: badge ? 8 : 0 }}>{label}</div>
      {badge && (
        <div style={{
          fontSize: 11.5, fontWeight: 600,
          color: badgePositive ? '#16a34a' : '#dc2626',
        }}>
          {badgePositive ? '↑' : '↓'} {badge}
        </div>
      )}
    </div>
  )
}

function buildMetricCards(category, metrics, analyst) {
  if (!metrics) return []
  const cards = []

  if (category === 'crypto') {
    cards.push({ icon: '💰', label: `${metrics.name || ''} Current Price`, value: fmtPrice(metrics.current_price), badge: metrics.price_change_24h != null ? `${Math.abs(metrics.price_change_24h).toFixed(2)}% 24h` : null, badgePositive: (metrics.price_change_24h || 0) >= 0 })
    if (metrics.market_cap) cards.push({ icon: '📊', label: 'Market Capitalization', value: fmt(metrics.market_cap, { prefix: '$', compact: true, decimals: 1 }), badge: 'Explosive growth', badgePositive: true })
    if (metrics.volume)     cards.push({ icon: '📈', label: '24h Trading Volume', value: fmt(metrics.volume, { prefix: '$', compact: true, decimals: 1 }), badge: 'High liquidity', badgePositive: true })
  }

  if (category === 'stock' || category === 'commodity') {
    cards.push({ icon: '📈', label: `${metrics.ticker || metrics.name || ''} Price`, value: fmtPrice(metrics.current_price), badge: metrics.price_change_24h != null ? `${Math.abs(metrics.price_change_24h).toFixed(2)}% today` : null, badgePositive: (metrics.price_change_24h || 0) >= 0 })
    if (metrics.market_cap) cards.push({ icon: '🏢', label: 'Market Cap', value: fmt(metrics.market_cap, { prefix: '$', compact: true, decimals: 1 }) })
    if (metrics.pe_ratio)   cards.push({ icon: '⚖️', label: 'P/E Ratio', value: `${metrics.pe_ratio.toFixed(1)}x` })
    if (analyst?.consensus_rating) cards.push({ icon: '🎯', label: 'Analyst Rating', value: analyst.consensus_rating.toUpperCase(), badge: analyst.total_analysts ? `${analyst.total_analysts} analysts` : null, badgePositive: true })
  }

  return cards.slice(0, 4)
}

export default function ResultsPanel({ jobData, query }) {
  const { result, metrics, chart_data, enrichments, category,
          data_confidence, classifier_confidence, fetched_at } = jobData

  const news    = enrichments?.news
  const analyst = enrichments?.analyst_ratings
  const onchain = enrichments?.onchain
  const funds   = enrichments?.fundamentals

  const insights = result?.insights || []
  const opps  = result?.opportunities?.length ? result.opportunities : insights.slice(0, Math.ceil(insights.length / 2))
  const risks = result?.risks?.length         ? result.risks         : insights.slice(Math.ceil(insights.length / 2))

  const hasChart  = ['crypto', 'stock', 'commodity'].includes(category) && chart_data
  const metCards  = buildMetricCards(category, metrics, analyst)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* ── Status bar ── */}
      <div className="fade-up" style={{
        background: '#f5c518', borderRadius: 10,
        padding: '12px 20px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', color: 'rgba(13,27,46,0.55)', marginBottom: 2 }}>ANALYSING</div>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#0d1b2e' }}>{query}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <ConfidenceBadge
            dataConfidence={data_confidence}
            classifierConfidence={classifier_confidence}
            fetchedAt={fetched_at}
          />
          <span style={{
            padding: '4px 12px', borderRadius: 100,
            background: 'rgba(13,27,46,0.1)', color: '#0d1b2e',
            fontSize: 11, fontWeight: 600,
          }}>⏱ Updated just now</span>
          <span style={{
            padding: '4px 12px', borderRadius: 100,
            background: '#0d1b2e', color: '#f5c518',
            fontSize: 11, fontWeight: 600,
          }}>✦ AI Analysed</span>
        </div>
      </div>

      {/* ── AI Market Summary ── */}
      <div className="fade-up" style={{
        background: '#0d1b2e', borderRadius: 14, padding: '26px 30px',
        animationDelay: '0.04s',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <span style={{ fontSize: 16 }}>📊</span>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#f5c518' }}>AI Market Summary</span>
        </div>
        <p style={{ fontSize: 14, color: 'rgba(255,255,255,0.82)', lineHeight: 1.8 }}>
          {result?.trend_summary || result?.balance || 'Generating summary...'}
        </p>
        {result?.tags?.length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 14 }}>
            {result.tags.map((tag, i) => (
              <span key={i} style={{
                padding: '3px 10px', borderRadius: 100,
                background: 'rgba(245,197,24,0.14)', border: '1px solid rgba(245,197,24,0.25)',
                fontSize: 11, color: 'rgba(255,255,255,0.7)', fontWeight: 500,
              }}>{tag}</span>
            ))}
          </div>
        )}
      </div>

      {/* ── Metric cards ── */}
      {metCards.length > 0 && (
        <div className="fade-up" style={{
          display: 'grid', gridTemplateColumns: `repeat(${metCards.length}, 1fr)`,
          gap: 14, animationDelay: '0.08s',
        }}>
          {metCards.map((c, i) => <MetricCard key={i} {...c} />)}
        </div>
      )}

      {/* ── News  +  Chart / Insights ── */}
      <div className="fade-up" style={{
        display: 'grid',
        gridTemplateColumns: news && hasChart ? '1fr 380px' : '1fr',
        gap: 16, alignItems: 'start',
        animationDelay: '0.12s',
      }}>
        {/* Left — news */}
        {news && <NewsPanel news={news} />}

        {/* Right — chart then key insights stacked */}
        {hasChart && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <MarketChart chartData={chart_data} category={category} />
            {insights.length > 0 && <KeyInsights insights={insights} />}
          </div>
        )}

        {/* No chart: key insights full-width below news */}
        {!hasChart && insights.length > 0 && <KeyInsights insights={insights} />}
      </div>

      {/* ── Opportunities + Risks ── */}
      <div className="fade-up" style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16,
        animationDelay: '0.16s',
      }}>
        {/* Opportunities */}
        <div className="card" style={{ padding: '22px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <span style={{ fontSize: 15 }}>✅</span>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#16a34a' }}>Opportunities</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {opps.length > 0 ? opps.map((opp, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <div style={{
                  width: 18, height: 18, borderRadius: '50%', flexShrink: 0, marginTop: 1,
                  background: '#f0fdf4', border: '1.5px solid #22c55e',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 9, color: '#16a34a', fontWeight: 700,
                }}>✓</div>
                <p style={{ fontSize: 13, color: '#0d1b2e', lineHeight: 1.65 }}>{opp}</p>
              </div>
            )) : (
              <p style={{ fontSize: 13, color: '#8896a7' }}>No specific opportunities identified.</p>
            )}
          </div>
        </div>

        {/* Risks */}
        <div className="card" style={{ padding: '22px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <span style={{ fontSize: 15 }}>⚠️</span>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#dc2626' }}>Risks to Watch</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {risks.length > 0 ? risks.map((risk, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <div style={{
                  width: 18, height: 18, borderRadius: '50%', flexShrink: 0, marginTop: 1,
                  background: '#fef2f2', border: '1.5px solid #ef4444',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 9, color: '#dc2626', fontWeight: 700,
                }}>!</div>
                <p style={{ fontSize: 13, color: '#0d1b2e', lineHeight: 1.65 }}>{risk}</p>
              </div>
            )) : (
              <p style={{ fontSize: 13, color: '#8896a7' }}>No specific risks flagged.</p>
            )}
          </div>
        </div>
      </div>

      {/* ── Actionable Advice ── */}
      {insights.length > 0 && (
        <div className="card fade-up" style={{ padding: '24px 28px', animationDelay: '0.2s' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 16 }}>🎯</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: '#0d1b2e' }}>Actionable Advice</span>
          </div>
          <p style={{ fontSize: 12, color: '#8896a7', marginBottom: 22 }}>Based on current market data and AI analysis</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
            {insights.slice(0, 3).map((ins, i) => {
              const sep   = ins.match(/[—–:]/)?.[0]
              const parts = sep ? ins.split(sep) : [null, ins]
              const title = parts[0]?.trim() || `Step ${i + 1}`
              const body  = parts.slice(1).join(sep || '').trim() || ins
              return (
                <div key={i} style={{ background: '#f7f8fa', borderRadius: 10, padding: '18px 16px' }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: '50%',
                    background: '#0d1b2e', color: '#f5c518',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 13, fontWeight: 700, marginBottom: 12,
                  }}>{i + 1}</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#0d1b2e', marginBottom: 6 }}>{title}</div>
                  <div style={{ fontSize: 12, color: '#4a5568', lineHeight: 1.65 }}>{body}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Supplemental: on-chain / fundamentals / analyst ── */}
      {(onchain || funds || analyst) && (
        <div style={{ display: 'grid', gridTemplateColumns: analyst ? '1fr 1fr' : '1fr', gap: 16 }}>
          {analyst && <AnalystPanel analyst={analyst} />}
          {(onchain || funds) && <SupplementalPanel onchain={onchain} funds={funds} analyst={null} />}
        </div>
      )}

      {/* ── Final Recommendations ── */}
      {result?.recommendations?.length > 0 && (
        <FinalRecommendationsPanel recommendations={result.recommendations} />
      )}

    </div>
  )
}

function KeyInsights({ insights }) {
  return (
    <div className="card" style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <span style={{ fontSize: 15 }}>🔑</span>
        <span style={{ fontSize: 14, fontWeight: 700, color: '#0d1b2e' }}>Key Insights</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {insights.map((ins, i) => (
          <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%',
              background: '#f5c518', flexShrink: 0, marginTop: 7,
            }} />
            <p style={{ fontSize: 13, color: '#0d1b2e', lineHeight: 1.65 }}>{ins}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function SupplementalPanel({ onchain, funds, analyst }) {
  const rows = []
  if (onchain?.chain_tvl_usd) rows.push({ label: 'Chain TVL', value: fmt(onchain.chain_tvl_usd, { prefix: '$', compact: true, decimals: 1 }), sub: onchain.chain_tvl_7d_change_pct != null ? `${onchain.chain_tvl_7d_change_pct > 0 ? '+' : ''}${onchain.chain_tvl_7d_change_pct.toFixed(1)}% 7d` : null })
  if (onchain?.active_addresses_24h) rows.push({ label: 'Active Addresses 24h', value: fmt(onchain.active_addresses_24h, { compact: true, decimals: 0 }) })
  if (onchain?.exchange_netflow_24h_usd != null) rows.push({ label: 'Exchange Netflow 24h', value: fmt(onchain.exchange_netflow_24h_usd, { prefix: '$', compact: true, decimals: 1 }) })
  if (analyst?.consensus_rating)    rows.push({ label: 'Analyst Consensus', value: analyst.consensus_rating.toUpperCase() })
  if (analyst?.target_price_consensus) rows.push({ label: 'Price Target', value: fmtPrice(analyst.target_price_consensus), sub: analyst.total_analysts ? `${analyst.total_analysts} analysts` : null })
  if (funds?.pe_ratio)           rows.push({ label: 'P/E Ratio', value: `${funds.pe_ratio.toFixed(1)}x` })
  if (funds?.net_margin_pct)     rows.push({ label: 'Net Margin', value: `${(funds.net_margin_pct * 100).toFixed(1)}%` })
  if (funds?.debt_to_equity)     rows.push({ label: 'Debt / Equity', value: funds.debt_to_equity.toFixed(2) })
  if (funds?.dividend_yield_pct) rows.push({ label: 'Dividend Yield', value: `${funds.dividend_yield_pct.toFixed(2)}%` })

  if (!rows.length) return null

  return (
    <div className="card fade-up" style={{ padding: '22px 26px', animationDelay: '0.24s' }}>
      <div style={{ fontSize: 14, fontWeight: 700, color: '#0d1b2e', marginBottom: 18 }}>📋 Additional Data</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 12 }}>
        {rows.map((r, i) => (
          <div key={i} style={{ background: '#f7f8fa', borderRadius: 8, padding: '12px 14px' }}>
            <div style={{ fontSize: 10.5, color: '#8896a7', marginBottom: 4 }}>{r.label}</div>
            <div style={{ fontSize: 17, fontWeight: 700, color: '#0d1b2e' }}>{r.value}</div>
            {r.sub && <div style={{ fontSize: 10.5, color: '#8896a7', marginTop: 2 }}>{r.sub}</div>}
          </div>
        ))}
      </div>
    </div>
  )
}
