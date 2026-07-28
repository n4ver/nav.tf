/**
 * CQRS API client — routes writes to the Command service and reads to the Query service.
 * Axios request interceptor attaches Authorization: Bearer <token> from localStorage.
 */

import axios from 'axios'

const commandBaseUrl = (import.meta.env.VITE_COMMAND_BASE_URL || '/api/v1/commands').replace(/\/$/, '')
const queryBaseUrl = (import.meta.env.VITE_QUERY_BASE_URL || '/api/v1/queries').replace(/\/$/, '')
const authBaseUrl = (import.meta.env.VITE_AUTH_BASE_URL || '/api/v1/auth').replace(/\/$/, '')

const TOKEN_KEY = 'tf2_auth_token'

export function getCommandBaseUrl() {
  return commandBaseUrl
}

export function getQueryBaseUrl() {
  return queryBaseUrl
}

export function getAuthBaseUrl() {
  return authBaseUrl
}

export function getStoredAuthToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function getSteamLoginUrl() {
  return `${authBaseUrl}/steam/login`
}

function formatAxiosError(error) {
  const status = error.response?.status
  const statusText = error.response?.statusText || 'Request failed'
  const detail =
    error.response?.data?.detail ??
    error.response?.data?.message ??
    error.message ??
    ''
  const detailText = typeof detail === 'string' ? detail : JSON.stringify(detail)
  if (status) {
    return new Error(`${status} ${statusText}${detailText ? `: ${detailText}` : ''}`)
  }
  return new Error(detailText || 'Network error')
}

export const apiClient = axios.create({
  headers: {
    Accept: 'application/json',
  },
})

apiClient.interceptors.request.use((config) => {
  const token = getStoredAuthToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

async function requestJson(url, options = {}) {
  try {
    const response = await apiClient.request({
      url,
      method: options.method || 'GET',
      data: options.body ? JSON.parse(options.body) : options.data,
      headers: options.headers,
    })
    if (response.status === 204) {
      return null
    }
    return response.data
  } catch (error) {
    throw formatAxiosError(error)
  }
}

// ── Auth ────────────────────────────────────────────────────────────────────

export async function fetchAuthMe() {
  return requestJson(`${authBaseUrl}/me`)
}

/**
 * Exchange a one-time Steam login code for a JWT.
 * @param {string} code
 */
export async function exchangeAuthCode(code) {
  return requestJson(`${authBaseUrl}/exchange`, {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

// ── Command service (writes) ───────────────────────────────────────────────

/**
 * Upload a raw TF2 log. Returns 202 Accepted with { match_id, status }.
 * @param {{ log_data: string, timestamp: string }} payload
 */
export async function uploadLog(payload) {
  return requestJson(`${commandBaseUrl}/logs/upload`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/**
 * Ingest a match by fetching JSON from logs.tf. Admin-only.
 * Returns 202 Accepted with { match_id, log_id, status }.
 * @param {{ logstf_id: number }} payload
 */
export async function ingestLogsTf(payload) {
  return requestJson(`${commandBaseUrl}/logs/ingest-logstf`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updatePlayerDisplayName(payload) {
  return requestJson(`${commandBaseUrl}/players/display-name`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function createTournament(payload) {
  return requestJson(`${commandBaseUrl}/tournaments`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateTournament(tournamentId, payload) {
  return requestJson(`${commandBaseUrl}/tournaments/${encodeURIComponent(tournamentId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

// ── Query service (reads) ──────────────────────────────────────────────────

/**
 * Paginated match list (materialized MatchSummaryView rows).
 * Backend uses skip/limit; returns an array (no total count).
 */
export async function fetchMatches({ skip = 0, limit = 20, tournamentId = null } = {}) {
  const params = new URLSearchParams({
    skip: String(skip),
    limit: String(limit),
  })
  if (tournamentId) {
    params.set('tournament_id', String(tournamentId))
  }
  return requestJson(`${queryBaseUrl}/matches?${params}`)
}

/**
 * Match detail: { match_summary, players: PlayerStatsView[] }
 */
export async function fetchMatchDetail(matchId) {
  return requestJson(`${queryBaseUrl}/matches/${encodeURIComponent(matchId)}`)
}

/**
 * Lifetime aggregated player stats (PlayerLifetimeStatsView).
 */
export async function fetchPlayerStats(steamId) {
  return requestJson(`${queryBaseUrl}/players/${encodeURIComponent(steamId)}/stats`)
}

/**
 * Tournament summary list (TournamentSummaryView[]).
 */
export async function fetchTournaments() {
  return requestJson(`${queryBaseUrl}/tournaments`)
}

/**
 * Tournament leaderboard (LeaderboardEntryView[]).
 */
export async function fetchTournamentLeaderboard(tournamentId, { className = null, limit = 50 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (className) {
    params.set('class_name', String(className))
  }
  return requestJson(
    `${queryBaseUrl}/tournaments/${encodeURIComponent(tournamentId)}/leaderboard?${params}`,
  )
}

/**
 * Lookup by match UUID, logs.tf ID, or SteamID.
 */
export async function searchQuery(query, { limit = 10 } = {}) {
  const params = new URLSearchParams({
    q: String(query),
    limit: String(limit),
  })
  return requestJson(`${queryBaseUrl}/search?${params}`)
}

/**
 * Class rating benchmark rows.
 */
export async function fetchClassBenchmarks() {
  return requestJson(`${queryBaseUrl}/benchmarks/class-rating`)
}

export async function fetchQueryHealth() {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error) {
    throw formatAxiosError(error)
  }
}
