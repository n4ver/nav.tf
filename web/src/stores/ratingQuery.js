import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchClassBenchmarks, fetchTournamentLeaderboard } from '../api'

/**
 * Query-side store for precomputed ratings: tournament leaderboard + class benchmarks.
 */
export const useRatingQueryStore = defineStore('ratingQuery', () => {
  const leaderboard = ref([])
  const leaderboardTournamentId = ref('')
  const leaderboardClassFilter = ref('')
  const leaderboardLoading = ref(false)
  const leaderboardError = ref('')

  const benchmarks = ref([])
  const benchmarksLoading = ref(false)
  const benchmarksError = ref('')

  async function loadLeaderboard(tournamentId, { className = '', limit = 50, force = false } = {}) {
    const id = String(tournamentId || '').trim()
    if (!id) {
      leaderboard.value = []
      leaderboardTournamentId.value = ''
      leaderboardError.value = ''
      return []
    }

    const nextClass = String(className || '')
    if (
      !force
      && leaderboardTournamentId.value === id
      && leaderboardClassFilter.value === nextClass
      && leaderboard.value.length
    ) {
      return leaderboard.value
    }

    leaderboardLoading.value = true
    leaderboardError.value = ''
    leaderboardTournamentId.value = id
    leaderboardClassFilter.value = nextClass

    try {
      const rows = await fetchTournamentLeaderboard(id, {
        className: nextClass || null,
        limit,
      })
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
