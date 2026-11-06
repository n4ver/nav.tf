<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import PlayerLeaderboard from '../components/stats/PlayerLeaderboard.vue'
import Panel from '../components/ui/Panel.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import StateMessage from '../components/ui/StateMessage.vue'
import { useEventQueryStore } from '../stores/eventQuery'
import { formatDate } from '../utils/format'

const props = defineProps({
  eventId: {
    type: String,
    default: '',
  },
})

const router = useRouter()
const eventQuery = useEventQueryStore()
const {
  events,
  eventsLoading,
  eventsError,
  eventDetail,
  eventDetailLoading,
  eventDetailError,
  leaderboard,
  leaderboardLoading,
  leaderboardError,
} = storeToRefs(eventQuery)

const selectedEvent = ref('')
const classFilter = ref('')

const eventMeta = computed(() => eventDetail.value?.event || null)
const childTournaments = computed(() => eventDetail.value?.tournaments || [])

/** Tournament dashboard deep link; TournamentView reads `?tournament=`. */
function tournamentPath(tournament) {
  return { name: 'tournament', query: { tournament: String(tournament.tournament_id) } }
}

function selectEvent(event) {
  selectedEvent.value = String(event.event_id)
  router.push({ name: 'event', params: { eventId: String(event.event_id) } })
}

async function loadSelected() {
  const id = selectedEvent.value
  if (!id) return
  await Promise.all([
    eventQuery.loadEventDetail(id, { force: true }),
    eventQuery.loadLeaderboard(id, { className: classFilter.value, limit: 50, force: true }),
  ])
}

onMounted(async () => {
  await eventQuery.loadEvents({ force: true })
  const fromRoute = String(props.eventId || '').trim()
  if (fromRoute) {
    selectedEvent.value = fromRoute
  } else if (events.value.length) {
    selectedEvent.value = String(events.value[0].event_id)
  }
  // The selectedEvent watcher performs the load.
})

watch(
  () => props.eventId,
  async (next) => {
    if (next && String(next) !== selectedEvent.value) {
      selectedEvent.value = String(next)
      await loadSelected()
    }
  },
)

watch(selectedEvent, async (eventId) => {
  if (!eventId) return
  if (String(props.eventId || '') !== String(eventId)) {
    router.replace({ name: 'event', params: { eventId } })
  }
  await loadSelected()
})

watch(classFilter, async () => {
  if (!selectedEvent.value) return
  await eventQuery.loadLeaderboard(selectedEvent.value, {
    className: classFilter.value,
    limit: 50,
    force: true,
  })
})
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-lg font-bold">Events</h1>

    <div v-if="eventsLoading" aria-busy="true" aria-label="Loading events">
      <SkeletonBlock :rows="4" height="h-10" />
    </div>

    <StateMessage v-else-if="eventsError" tone="error">{{ eventsError }}</StateMessage>

    <Panel v-else-if="!events.length" title="Events">
      <StateMessage>No events yet. Create one from Admin → Events.</StateMessage>
    </Panel>

    <div v-else class="grid gap-3 lg:grid-cols-[260px_minmax(0,1fr)]">
      <Panel title="All events" flush>
        <ul class="list-none" aria-label="Events">
          <li v-for="event in events" :key="event.event_id" class="border-b border-line last:border-b-0">
            <button
              type="button"
              class="focus-ring flex w-full items-center justify-between gap-2 border-l-2 px-3 py-2 text-left text-sm hover:bg-surface-700"
              :class="
                String(event.event_id) === selectedEvent
                  ? 'border-accent bg-surface-700 text-ink'
                  : 'border-transparent text-ink-muted'
              "
              :aria-pressed="String(event.event_id) === selectedEvent"
              @click="selectEvent(event)"
            >
              <span class="truncate font-semibold">{{ event.name }}</span>
              <span class="shrink-0 text-xs tabular-nums">{{ Number(event.tournament_count) || 0 }} t.</span>
            </button>
          </li>
        </ul>
      </Panel>

      <div class="min-w-0 space-y-3">
        <div v-if="eventDetailLoading" aria-busy="true" aria-label="Loading event">
          <SkeletonBlock :rows="1" height="h-24" />
        </div>
        <StateMessage v-else-if="eventDetailError" tone="error">{{ eventDetailError }}</StateMessage>

        <Panel v-else-if="eventMeta" :title="eventMeta.name">
          <template #actions>
            <span class="text-xs text-ink-muted">
              {{ eventMeta.tournament_count }} tournaments · {{ eventMeta.match_count }} matches
            </span>
          </template>
          <dl class="mb-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
            <template v-if="eventMeta.start_date">
              <dt class="text-ink-muted">Starts</dt>
              <dd>{{ formatDate(eventMeta.start_date) }}</dd>
            </template>
            <template v-if="eventMeta.end_date">
              <dt class="text-ink-muted">Ends</dt>
              <dd>{{ formatDate(eventMeta.end_date) }}</dd>
            </template>
          </dl>
          <h3 class="mb-1 text-xs font-bold uppercase tracking-wide text-ink-muted">Tournaments</h3>
          <ul v-if="childTournaments.length" class="flex list-none flex-wrap gap-2">
            <li v-for="tournament in childTournaments" :key="tournament.tournament_id">
              <RouterLink class="tab" :to="tournamentPath(tournament)">
                {{ tournament.name }}
                <span class="ml-1.5 tabular-nums opacity-70">{{ tournament.match_count }}</span>
              </RouterLink>
            </li>
          </ul>
          <StateMessage v-else>No tournaments linked yet.</StateMessage>
        </Panel>

        <Panel v-if="selectedEvent && !eventDetailError" title="Event leaderboard" flush>
          <PlayerLeaderboard
            v-model:class-filter="classFilter"
            :rows="leaderboard"
            :loading="leaderboardLoading"
            :error="leaderboardError"
            empty-message="No event stats yet."
          />
        </Panel>
      </div>
    </div>
  </div>
</template>
