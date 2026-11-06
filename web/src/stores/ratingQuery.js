import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchClassBenchmarks,
  fetchEventLeaderboard,
  fetchGlobalLeaderboard,
  fetchTournamentLeaderboard,
} from '../api'

/**
 * Query-side store for ratings: the home-page leaderboard (one tournament, one
 * event's tournaments, or everything) + class benchmarks.
 */
export const useRatingQueryStore = defineStore('ratingQuery', () => {
  const leaderboard = ref([])
  const leaderboardTournamentId = ref('')
  const leaderboardScope = ref('')
  const leaderboardClassFilter = ref('')
  const leaderboardLoading = ref(false)
  const leaderboardError = ref('')

  const benchmarks = ref([])
  const benchmarksLoading = ref(false)
  const benchmarksError = ref('')

  /**
   * @param {string} tournamentId  tournament scope; empty = aggregate scope
   * @param {{ eventId?: string, className?: string, limit?: number, force?: boolean }} [options]
   *   `eventId` narrows the aggregate scope to one event; with neither id the
   *   leaderboard covers every match.
   */
  async function loadLeaderboard(
    tournamentId,
    { eventId = '', className = '', limit = 50, force = false } = {},
  ) {
    const id = String(tournamentId || '').trim()
    const event = id ? '' : String(eventId || '').trim()
    const scopeKey = id ? `t:${id}` : event ? `e:${event}` : 'all'

    const nextClass = String(className || '')
    if (
      !force
      && leaderboardScope.value === scopeKey
      && leaderboardClassFilter.value === nextClass
      && leaderboard.value.length
    ) {
      return leaderboard.value
    }

    leaderboardLoading.value = true
    leaderboardError.value = ''
    leaderboardScope.value = scopeKey
    leaderboardTournamentId.value = id
    leaderboardClassFilter.value = nextClass

    try {
      const options = { className: nextClass || null, limit }
      const rows = id
        ? await fetchTournamentLeaderboard(id, options)
        : event
          ? await fetchEventLeaderboard(event, options)
          : await fetchGlobalLeaderboard(options)
      // A newer request may have changed the scope while this one was in flight.
      if (leaderboardScope.value !== scopeKey || leaderboardClassFilter.value !== nextClass) {
        return leaderboard.value
      }
      leaderboard.value = Array.isArray(rows) ? rows : []
      return leaderboard.value
    } catch (err) {
      leaderboard.value = []
      leaderboardError.value = err instanceof Error ? err.message : 'Failed to load leaderboard'
      return []
    } finally {
      leaderboardLoading.value = false
    }
  }

  async function loadBenchmarks({ force = false } = {}) {
    if (!force && benchmarks.value.length) {
      return benchmarks.value
    }

    benchmarksLoading.value = true
    benchmarksError.value = ''
    try {
      const rows = await fetchClassBenchmarks()
      benchmarks.value = Array.isArray(rows) ? rows : []
      return benchmarks.value
    } catch (err) {
      benchmarks.value = []
      benchmarksError.value = err instanceof Error ? err.message : 'Failed to load benchmarks'
      return []
    } finally {
      benchmarksLoading.value = false
    }
  }

  function invalidate() {
    leaderboard.value = []
    leaderboardTournamentId.value = ''
    leaderboardScope.value = ''
    leaderboardClassFilter.value = ''
    benchmarks.value = []
  }

  return {
    leaderboard,
    leaderboardTournamentId,
    leaderboardClassFilter,
    leaderboardLoading,
    leaderboardError,
    benchmarks,
    benchmarksLoading,
    benchmarksError,
    loadLeaderboard,
    loadBenchmarks,
    invalidate,
  }
})
