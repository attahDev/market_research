import { useState } from 'react'
import HeroSearch from './HeroSearch'
import ExportButton from './ExportButton'
import AnalyzingPanel from './AnalyzingPanel'
import ResultsPanel from './ResultsPanel'

const EXAMPLE_CARDS = [
  { emoji: '🌿', title: 'Sustainable Fashion', desc: 'Market size, trends & opportunities in Africa' },
  { emoji: '🏦', title: 'Fintech in West Africa', desc: 'Growth drivers, players & entry points' },
  { emoji: '🤖', title: 'AI SaaS Trends', desc: 'Demand signals, competition & niches' },
]

function ExampleCard({ emoji, title, desc, onClick }) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '20px 18px', textAlign: 'left', cursor: 'pointer',
        background: '#ffffff',
        border: hovered ? '1.5px solid #f5c518' : '1.5px solid #e2e6ea',
        borderRadius: 14,
        boxShadow: hovered
          ? '0 4px 16px rgba(245,197,24,0.15)'
          : '0 1px 3px rgba(0,0,0,0.06)',
        transform: hovered ? 'translateY(-2px)' : 'translateY(0)',
        transition: 'all 0.15s',
        fontFamily: 'Inter, sans-serif',
      }}
    >
      <div style={{ fontSize: 24, marginBottom: 10 }}>{emoji}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: '#0d1b2e', marginBottom: 5 }}>{title}</div>
      <div style={{ fontSize: 12, color: '#8896a7', lineHeight: 1.5 }}>{desc}</div>
    </button>
  )
}

function EmptyState({ onSubmit }) {
  return (
    <div className="fade-up" style={{ textAlign: 'center', paddingTop: 40 }}>
      {/* Icon */}
      <div style={{
        width: 82, height: 82, borderRadius: '50%',
        background: '#fef9e7', border: '3px solid #f5c518',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 34, margin: '0 auto 20px',
      }}>📊</div>

      <h2 style={{ fontSize: 20, fontWeight: 700, color: '#0d1b2e', marginBottom: 10 }}>
        What Market do you want to explore?
      </h2>
      <p style={{
        fontSize: 14, color: '#4a5568',
        maxWidth: 440, margin: '0 auto 36px', lineHeight: 1.7,
      }}>
        Type any market, industry, or business opportunity above and our AI
        will deliver deep insights, trends, competitor data, and actionable
        opportunities in seconds.
      </p>

      {/* Example cards */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 16, maxWidth: 720, margin: '0 auto',
      }}>
        {EXAMPLE_CARDS.map(card => (
          <ExampleCard
            key={card.title}
            {...card}
            onClick={() => onSubmit(card.title)}
          />
        ))}
      </div>
    </div>
  )
}

function ErrorPanel({ error, onRetry }) {
  return (
    <div className="card fade-up" style={{
      padding: 32, textAlign: 'center',
      maxWidth: 480, margin: '40px auto 0',
    }}>
      <div style={{
        width: 48, height: 48, borderRadius: '50%',
        background: '#fef2f2', color: '#ef4444',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 20, margin: '0 auto 16px',
      }}>⚠</div>
      <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>Research Failed</h3>
      <p style={{ fontSize: 13, color: '#4a5568', marginBottom: 20, lineHeight: 1.6 }}>
        {error?.message || 'Something went wrong. Please try again.'}
      </p>
      <button
        onClick={onRetry}
        style={{
          padding: '9px 24px', borderRadius: 8,
          background: '#f5c518', color: '#0d1b2e',
          border: 'none', fontWeight: 600, fontSize: 14,
          cursor: 'pointer', fontFamily: 'Inter, sans-serif',
        }}
      >Try Again</button>
    </div>
  )
}

export default function MarketResearchPage({
  phase,
  currentQuery,
  statusLabel,
  jobData,
  errorInfo,
  onSubmit,
  onCancel,
  onNewSearch,
}) {
  const showLoading = phase === 'loading'
  const showResult  = phase === 'result' && jobData
  const showError   = phase === 'error'
  const showEmpty   = !showLoading && !showResult && !showError

  return (
    <div style={{
      minHeight: '100%',
      background: '#f0f2f5',
      fontFamily: 'Inter, sans-serif',
    }}>

      {/* ── Top action bar ── */}
      <div style={{
        display: 'flex', justifyContent: 'flex-end',
        padding: '16px 28px 0',
      }}>
        {showResult ? (
          <div style={{ display: 'flex', gap: 10 }}>
            <ExportButton query={currentQuery} jobData={jobData} />
            <button
              onClick={onNewSearch}
              style={{
                padding: '8px 16px', borderRadius: 8,
                background: '#e63946', color: '#fff',
                border: 'none', fontWeight: 600, fontSize: 13,
                cursor: 'pointer', fontFamily: 'Inter, sans-serif',
                display: 'flex', alignItems: 'center', gap: 6,
              }}
            >+ New Project</button>
          </div>
        ) : (
          <button
            onClick={onNewSearch}
            style={{
              padding: '8px 16px', borderRadius: 8,
              background: '#e63946', color: '#fff',
              border: 'none', fontWeight: 600, fontSize: 13,
              cursor: 'pointer', fontFamily: 'Inter, sans-serif',
              display: 'flex', alignItems: 'center', gap: 6,
            }}
          >+ New Project</button>
        )}
      </div>

      {/* ── Hero search — always visible ── */}
      <div style={{ padding: '16px 28px 0' }}>
        <HeroSearch
          onSubmit={onSubmit}
          defaultQuery={currentQuery}
          disabled={showLoading}
        />
      </div>

      {/* ── Page body ── */}
      <div style={{ padding: '24px 28px 60px' }}>
        {showLoading && (
          <AnalyzingPanel
            query={currentQuery}
            status={statusLabel}
            onCancel={onCancel}
          />
        )}
        {showResult && (
          <ResultsPanel
            jobData={jobData}
            query={currentQuery}
            onNewSearch={onNewSearch}
          />
        )}
        {showError && (
          <ErrorPanel error={errorInfo} onRetry={onNewSearch} />
        )}
        {showEmpty && (
          <EmptyState onSubmit={onSubmit} />
        )}
      </div>
    </div>
  )
}
