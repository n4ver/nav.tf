import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchMatchDetail, fetchMatches } from '../api'

/**
 * Query-side store: match list + match detail materialized views.
 */
export const useMatchQueryStore = defineStore('matchQuery', () => {
  const matches = ref([])
  const matchesPage = ref(1)
  const matchesPageSize = ref(20)
  const matchesHasMore = ref(false)
  const matchesLoading = ref(false)
  const matchesError = ref('')

  const matchDetail = ref(null)
  const matchDetailId = ref(null)
  const matchDetailLoading = ref(false)
  const matchDetailError = ref('')

  /** Simple in-memory cache keyed by match_id */
  const detailCache = ref(new Map())

  const matchSummary = computed(() => matchDetail.value?.match_summary ?? null)
  const matchPlayers = computed(() => {
    const rows = matchDetail.value?.players ?? []
    return [...rows].sort((a, b) => {
      const left = typeof a?.rating === 'number' ? a.rating : 1
      const right = typeof b?.rating === 'number' ? b.rating : 1
      return right - left
    })
  })

  async function loadMatches({
    page = matchesPage.value,
    pageSize = matchesPageSize.value,
    tournamentId = null,
    eventId = null,
  } = {}) {
    const safePage = Math.max(1, Number(page) || 1)
    const safeSize = Math.min(100, Math.max(1, Number(pageSize) || 20))
    const skip = (safePage - 1) * safeSize

    matchesLoading.value = true
    matchesError.value = ''

    try {
      const rows = await fetchMatches({ skip, limit: safeSize, tournamentId, eventId })
      const list = Array.isArray(rows) ? rows : []
      matches.value = list
      matchesPage.value = safePage
      matchesPageSize.value = safeSize
      matchesHasMore.value = list.length === safeSize
    } catch (err) {
      matches.value = []
      matchesHasMore.value = false
      matchesError.value = err instanceof Error ? err.message : 'Failed to load matches'
    } finally {
      matchesLoading.value = false
    }
  }

  async function loadMatchDetail(matchId, { force = false } = {}) {
    const id = String(matchId || '').trim()
    if (!id) {
      matchDetail.value = null
      matchDetailId.value = null
      matchDetailError.value = 'Match ID is required'
      return null
    }

    if (!force && detailCache.value.has(id)) {
      const cached = detailCache.value.get(id)
      const summary = cached?.match_summary
      // Bypass stale cache entries from before scores/CDM fields were exposed.
      if (summary && 'blu_score' in summary && 'red_score' in summary) {
        matchDetail.value = cached
        matchDetailId.value = id
        matchDetailError.value = ''
        return matchDetail.value
      }
    }

    matchDetailLoading.value = true
    matchDetailError.value = ''
    matchDetailId.value = id

    try {
      const detail = await fetchMatchDetail(id)
      matchDetail.value = detail
      const next = new Map(detailCache.value)
      next.set(id, detail)
      detailCache.value = next
      return detail
    } catch (err) {
      matchDetail.value = null
      matchDetailError.value = err instanceof Error ? err.message : 'Failed to load match'
      return null
    } finally {
      matchDetailLoading.value = false
    }
  }

  function invalidateMatch(matchId) {
    if (!matchId) {
      return
    }
    const next = new Map(detailCache.value)
    next.delete(String(matchId))
    detailCache.value = next
  }

  function clearMatchDetail() {
    matchDetail.value = null
    matchDetailId.value = null
    matchDetailError.value = ''
  }

  return {
    matches,
    matchesPage,
    matchesPageSize,
    matchesHasMore,
    matchesLoading,
    matchesError,
    matchDetail,
    matchDetailId,
    matchDetailLoading,
    matchDetailError,
    matchSummary,
    matchPlayers,
    loadMatches,
    loadMatchDetail,
    invalidateMatch,
    clearMatchDetail,
  }
})
