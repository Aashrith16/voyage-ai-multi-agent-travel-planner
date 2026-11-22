export const API_URL = import.meta.env.VITE_API_URL || (
  import.meta.env.DEV
    ? 'http://127.0.0.1:8000'
    : 'https://voyageai-backend-5pf8.onrender.com'
)

export async function apiRequest(path, { token, method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`

  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch {
    throw new Error('Could not connect to VoyageAI. Check that the API is running and try again.')
  }

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : ''
    if (response.status === 401) throw new Error('Please sign in again to continue.')
    if (response.status === 429) throw new Error('A planning service is temporarily busy. Please try again shortly.')
    if (response.status === 502 && data.error?.code === 'destination_research_unavailable') {
      throw new Error('Destination research is temporarily unavailable. Please try again shortly.')
    }
    if (/https?:\/\/|traceback|api\.open-meteo/i.test(detail) || response.status >= 500) {
      throw new Error('VoyageAI could not complete this request. A service may be temporarily unavailable; please try again shortly.')
    }
    throw new Error(detail || 'VoyageAI could not complete this request.')
  }
  return data
}
