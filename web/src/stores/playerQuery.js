import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchPlayerStats } from '../api'
import { convertToSteamID64 } from '../utils/steam'

/**
 * Query-side store: lifetime player statistics materialized view.
 */
export const usePlayerQueryStore = defineStore('playerQuery', () => {
  const stats = ref(null)
  const steamId = ref('')
  const loading = ref(false)
  const error = ref('')

  /** Cache keyed by steam_id */
  const cache = ref(new Map())

  async function loadPlayerStats(nextSteamId, { force = false } = {}) {
    const raw = String(nextSteamId || '').trim()
    const id = convertToSteamID64(raw) || raw
    if (!id) {
      stats.value = null
      steamId.value = ''
      error.value = 'Steam ID is required'
      return null
    }

    if (!force && cache.value.has(id)) {
      stats.value = cache.value.get(id)
      steamId.value = id
      error.value = ''
      return stats.value
    }

    loading.value = true
    error.value = ''
    steamId.value = id

    try {
      const payload = await fetchPlayerStats(id)
      stats.value = payload
      const next = new Map(cache.value)
      next.set(id, payload)
      cache.value = next
      return payload
    } catch (err) {
      stats.value = null
      error.value = err instanceof Error ? err.message : 'Failed to load player stats'
      return null
    } finally {
      loading.value = false
    }
  }

  function invalidate(steamIdKey) {
    if (!steamIdKey) {
      return
    }
    const next = new Map(cache.value)
    next.delete(String(steamIdKey))
    cache.value = next
  }

  function clear() {
    stats.value = null
    steamId.value = ''
    error.value = ''
    cache.value = new Map()
  }

  return {
    stats,
    steamId,
    loading,
    error,
    loadPlayerStats,
    invalidate,
    clear,
  }
})
