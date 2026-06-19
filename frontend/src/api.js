const BASE = '/api/v1'

export async function submitQuery(query) {
  const res = await fetch(`${BASE}/research`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
  const data = await res.json()
  if (!data.success) throw new Error(data.error?.message || 'Submission failed')
  return data.data.job_id
}

export async function pollJob(jobId) {
  const res = await fetch(`${BASE}/research/${jobId}`)
  const data = await res.json()
  if (!data.success) throw new Error(data.error?.message || 'Poll failed')
  if (!data.data) throw new Error('Empty response from server')
  return data.data
}

export async function cancelJob(jobId) {
  const res = await fetch(`${BASE}/research/${jobId}`, { method: 'DELETE' })
  return await res.json()
}


const RECENT_KEY = 'mr_recent_searches'
const MAX_RECENT = 8

export function getRecentSearches() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
  } catch {
    return []
  }
}

export function addRecentSearch(query) {
  const recent = getRecentSearches().filter(q => q !== query)
  recent.unshift(query)
  localStorage.setItem(RECENT_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)))
}

export function removeRecentSearch(query) {
  const recent = getRecentSearches().filter(q => q !== query)
  localStorage.setItem(RECENT_KEY, JSON.stringify(recent))
}

export function clearRecentSearches() {
  localStorage.removeItem(RECENT_KEY)
}
