/**
 * Helpers for the CQRS RatingService 0–2 band (1.0 ≈ class average).
 */

export const RATING_MIN = 0
export const RATING_MAX = 2
export const RATING_NEUTRAL = 1

export function toRating(value) {
  // Number(null) and Number('') are 0; a missing rating must stay missing.
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function formatRating(value, digits = 3) {
  const n = toRating(value)
  if (n == null) return '—'
  return n.toFixed(digits)
}

/** CSS modifier: below / near / above the neutral 1.0 baseline. */
export function ratingTone(value) {
  const n = toRating(value)
  if (n == null) return 'unknown'
  if (n < 0.85) return 'low'
  if (n > 1.15) return 'high'
  return 'mid'
}

export function sortByRatingDesc(rows, ratingKey = 'rating') {
  return [...(rows || [])].sort((a, b) => {
    const left = toRating(a?.[ratingKey]) ?? RATING_NEUTRAL
    const right = toRating(b?.[ratingKey]) ?? RATING_NEUTRAL
    return right - left
  })
}
