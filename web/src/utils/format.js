/**
 * Shared display formatters and route helpers used across views.
 */

/** TF2 classes accepted by the leaderboard `class_name` filter. */
export const TF2_CLASSES = [
  'scout',
  'soldier',
  'pyro',
  'demoman',
  'heavyweapons',
  'engineer',
  'medic',
  'sniper',
  'spy',
]

/** Fixed-precision number; numeric strings are accepted, missing values render as an em dash. */
export function formatNumber(value, digits = 2) {
  if (value == null || value === '') return '—'
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n.toFixed(digits) : '—'
}

export function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

/** `754` → `12m 34s`. */
export function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0))
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}m ${String(secs).padStart(2, '0')}s`
}

/** `754` → `12m` (compact list cells). */
export function formatMinutes(seconds) {
  const total = Math.max(0, Number(seconds) || 0)
  return `${Math.floor(total / 60)}m`
}

/** Accepts either a 0–1 fraction or a 0–100 percentage. */
export function formatAccuracy(value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return '—'
  if (n <= 1) return `${(n * 100).toFixed(1)}%`
  return `${n.toFixed(1)}%`
}

export function classesLabel(classesPlayed) {
  if (!Array.isArray(classesPlayed) || !classesPlayed.length) return '—'
  return classesPlayed.join(', ')
}

export function errorMessage(error, fallback) {
  return error instanceof Error && error.message ? error.message : fallback
}

export function matchPath(matchId) {
  return `/match/${encodeURIComponent(String(matchId))}`
}

export function playerPath(steamId) {
  return `/player/${encodeURIComponent(String(steamId))}`
}
