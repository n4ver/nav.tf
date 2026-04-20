const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export function getApiBaseUrl() {
  return apiBaseUrl
}

export async function fetchJson(path) {
  const response = await fetch(`${apiBaseUrl}${path}`)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`${response.status} ${response.statusText}${text ? `: ${text}` : ''}`)
  }
  return response.json()
}
