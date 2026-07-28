/**
 * Steam ID helpers and player label formatting.
 */

const STEAM64_BASE = 76561197960265728n
const STEAM_ID3_RE = /^\[U:\d:(\d+)\]$/
const STEAM_ID_RE = /^STEAM_[0-5]:([01]):(\d+)$/i

export function convertToSteamID64(steamId) {
  const value = String(steamId || '').trim()
  if (!value) return null
  if (/^\d{17}$/.test(value)) return value

  const id3 = value.match(STEAM_ID3_RE)
  if (id3) {
    return (BigInt(id3[1]) + STEAM64_BASE).toString()
  }

  const legacy = value.match(STEAM_ID_RE)
  if (legacy) {
    const y = BigInt(legacy[1])
    const z = BigInt(legacy[2])
    const accountId = z * 2n + y
    return (accountId + STEAM64_BASE).toString()
  }

  return null
}

export function createSteamURL(steamIdOr64) {
  const steam64 = convertToSteamID64(steamIdOr64) || steamIdOr64
  if (!steam64) return null
  return `https://steamcommunity.com/profiles/${steam64}`
}

export function formatPlayerLabel(entry) {
  if (!entry) return '—'
  const name = entry.display_name || entry.persona_name
  if (name && String(name).trim()) {
    return String(name).trim()
  }
  return entry.steam_id || '—'
}
