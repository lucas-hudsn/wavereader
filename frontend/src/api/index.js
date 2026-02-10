const API_BASE = '/api'

export async function fetchStates() {
  const response = await fetch(`${API_BASE}/states`)
  if (!response.ok) throw new Error('Failed to fetch states')
  const data = await response.json()
  return data.states
}

export async function fetchBreaks() {
  const response = await fetch(`${API_BASE}/breaks`)
  if (!response.ok) throw new Error('Failed to fetch breaks')
  const data = await response.json()
  return data.breaks
}

export async function fetchBreaksByState(state) {
  const response = await fetch(`${API_BASE}/breaks/${encodeURIComponent(state)}`)
  if (!response.ok) throw new Error('Failed to fetch breaks')
  const data = await response.json()
  return data.breaks
}

export async function fetchBreakDetail(breakName) {
  const response = await fetch(`${API_BASE}/break/${encodeURIComponent(breakName)}`)
  if (!response.ok) throw new Error('Failed to fetch break details')
  const data = await response.json()
  if (data.error) throw new Error(data.error)
  return data
}
