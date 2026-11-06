import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchEventDetail, fetchEventLeaderboard, fetchEvents } from '../api'

export const useEventQueryStore = defineStore('eventQuery', () => {
  const events = ref([])
  const eventsLoading = ref(false)
  const eventsError = ref('')

  const eventDetail = ref(null)
  const eventDetailId = ref('')
  const eventDetailLoading = ref(false)
  const eventDetailError = ref('')

  const leaderboard = ref([])
  const leaderboardEventId = ref('')
  const leaderboardClassFilter = ref('')
  const leaderboardLoading = ref(false)
  const leaderboardError = ref('')

  async function loadEvents({ force = false } = {}) {
    if (!force && events.value.length) {
      return events.value
    }
    eventsLoading.value = true
    eventsError.value = ''
    try {
      const rows = await fetchEvents()
      events.value = Array.isArray(rows) ? rows : []
      return events.value
    } catch (err) {
      events.value = []
      eventsError.value = err instanceof Error ? err.message : 'Failed to load events'
      return []
    } finally {
      eventsLoading.value = false
    }
  }

  async function loadEventDetail(eventId, { force = false } = {}) {
    const id = String(eventId || '').trim()
    if (!id) {
      eventDetail.value = null
      eventDetailId.value = ''
      eventDetailError.value = ''
      return null
    }
    if (!force && eventDetailId.value === id && eventDetail.value) {
      return eventDetail.value
    }
    eventDetailLoading.value = true
    eventDetailError.value = ''
    eventDetailId.value = id
    try {
      eventDetail.value = await fetchEventDetail(id)
      return eventDetail.value
    } catch (err) {
      eventDetail.value = null
      eventDetailError.value = err instanceof Error ? err.message : 'Failed to load event'
      return null
    } finally {
      eventDetailLoading.value = false
    }
  }

  async function loadLeaderboard(eventId, { className = '', limit = 50, force = false } = {}) {
    const id = String(eventId || '').trim()
    if (!id) {
      leaderboard.value = []
      return []
    }
    const nextClass = String(className || '')
    if (
      !force
      && leaderboardEventId.value === id
      && leaderboardClassFilter.value === nextClass
      && leaderboard.value.length
    ) {
      return leaderboard.value
    }
    leaderboardLoading.value = true
    leaderboardError.value = ''
    leaderboardEventId.value = id
    leaderboardClassFilter.value = nextClass
    try {
      const rows = await fetchEventLeaderboard(id, {
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

  function invalidate() {
    events.value = []
    eventDetail.value = null
    eventDetailId.value = ''
    leaderboard.value = []
    leaderboardEventId.value = ''
    leaderboardClassFilter.value = ''
  }

  return {
    events,
    eventsLoading,
    eventsError,
    eventDetail,
    eventDetailId,
    eventDetailLoading,
    eventDetailError,
    leaderboard,
    leaderboardEventId,
    leaderboardClassFilter,
    leaderboardLoading,
    leaderboardError,
    loadEvents,
    loadEventDetail,
    loadLeaderboard,
    invalidate,
  }
})
