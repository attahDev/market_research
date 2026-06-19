import { useState, useRef, useCallback, useEffect } from 'react'
import { submitQuery, pollJob, cancelJob, addRecentSearch } from './api'
import MarketResearchPage from './components/MarketResearchPage'

const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS  = 5 * 60 * 1000

export default function App() {
  const [phase, setPhase]           = useState('search')
  const [jobId, setJobId]           = useState(null)
  const [jobData, setJobData]       = useState(null)
  const [currentQuery, setCurrentQuery] = useState('')
  const [statusLabel, setStatusLabel]   = useState('pending')
  const [errorInfo, setErrorInfo]   = useState(null)

  const pollRef    = useRef(null)
  const timeoutRef = useRef(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current)    clearInterval(pollRef.current)
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    pollRef.current = timeoutRef.current = null
  }, [])

  const startPolling = useCallback((jid) => {
    const poll = async () => {
      try {
        const data = await pollJob(jid)
        setStatusLabel(data.status)
        setJobData(data)
        if (['complete', 'failed', 'cancelled'].includes(data.status)) {
          stopPolling()
          if (data.status === 'complete')  setPhase('result')
          else if (data.status === 'failed') {
            setPhase('error')
            setErrorInfo(data.error || { code: 'UNKNOWN', message: 'Job failed' })
          } else {
            setPhase('search')
          }
        }
      } catch (err) {
        stopPolling()
        setPhase('error')
        setErrorInfo({ code: 'POLL_ERROR', message: err.message })
      }
    }
    poll()
    pollRef.current    = setInterval(poll, POLL_INTERVAL_MS)
    timeoutRef.current = setTimeout(() => {
      stopPolling()
      setPhase('error')
      setErrorInfo({ code: 'TIMEOUT', message: 'Research timed out after 5 minutes.' })
    }, POLL_TIMEOUT_MS)
  }, [stopPolling])

  const handleSubmit = useCallback(async (query) => {
    stopPolling()
    setCurrentQuery(query)
    setJobData(null)
    setErrorInfo(null)
    setStatusLabel('pending')
    setPhase('loading')
    addRecentSearch(query)
    try {
      const jid = await submitQuery(query)
      setJobId(jid)
      startPolling(jid)
    } catch (err) {
      setPhase('error')
      setErrorInfo({ code: 'SUBMIT_ERROR', message: err.message })
    }
  }, [startPolling, stopPolling])

  const handleCancel = useCallback(async () => {
    stopPolling()
    if (jobId) await cancelJob(jobId).catch(() => {})
    setPhase('search')
    setJobId(null)
    setJobData(null)
  }, [jobId, stopPolling])

  const handleNewSearch = useCallback(() => {
    stopPolling()
    setPhase('search')
    setJobId(null)
    setJobData(null)
    setErrorInfo(null)
    setCurrentQuery('')
  }, [stopPolling])

  useEffect(() => {
    const handler = (evt) => {
      const { type, payload } = evt.data || {}
      if (type === 'MR_ANALYZE' && payload?.query) {
        if (payload.autoSubmit !== false) {
          handleSubmit(payload.query)
        } else {
          setCurrentQuery(payload.query)
        }
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [handleSubmit])


  useEffect(() => {
    if (phase === 'result' && jobData) {
      window.parent?.postMessage({ type: 'MR_RESULT', payload: jobData }, '*')
    }
  }, [phase, jobData])

  useEffect(() => () => stopPolling(), [stopPolling])

  return (
    <MarketResearchPage
      phase={phase}
      currentQuery={currentQuery}
      statusLabel={statusLabel}
      jobData={jobData}
      errorInfo={errorInfo}
      onSubmit={handleSubmit}
      onCancel={handleCancel}
      onNewSearch={handleNewSearch}
    />
  )
}
