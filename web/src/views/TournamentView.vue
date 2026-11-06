<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute } from 'vue-router'
import { fetchEvents, fetchTournaments } from '../api'
import MatchResultList from '../components/match/MatchResultList.vue'
import PlayerLeaderboard from '../components/stats/PlayerLeaderboard.vue'
import DataGrid from '../components/ui/DataGrid.vue'
import Panel from '../components/ui/Panel.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import StateMessage from '../components/ui/StateMessage.vue'
import { useCan } from '../composables/useCan'
import { useMatchQueryStore } from '../stores/matchQuery'
import { useRatingQueryStore } from '../stores/ratingQuery'
import { errorMessage, formatDate } from '../utils/format'
import { formatRating, ratingTone } from '../utils/rating'

const route = useRoute()
const { allowed: canAdmin } = useCan('ADMIN')
const matchQuery = useMatchQueryStore()
const ratingQuery = useRatingQueryStore()
const { matches, matchesLoading, matchesError } = storeToRefs(matchQuery)
const {
  leaderboard,
  leaderboardLoading,
  leaderboardError,
  benchmarks,
  benchmarksLoading,
  benchmarksError,
} = storeToRefs(ratingQuery)

const tournaments = ref([])
const tournamentsLoading = ref(false)
const tournamentsError = ref('')
const selectedTournament = ref('')
const classFilter = ref('')
const events = ref([])
const selectedEvent = ref('')

const visibleTournaments = computed(() => {
  if (!selectedEvent.value) return tournaments.value
  return tournaments.value.filter((row) => String(row.event_id || '') === String(selectedEvent.value))
})

const selectedTournamentMeta = computed(
  () => tournaments.value.find((t) => String(t.tournament_id) === selectedTournament.value) || null,
)

const selectedEventName = computed(() => {
  const id = selectedTournamentMeta.value?.event_id
  return id ? events.value.find((e) => String(e.event_id) === String(id))?.name || '' : ''
})

const benchmarkColumns = [
  { key: 'class_name', label: 'Class', sortable: true },
  { key: 'sample_size', label: 'n', sortable: true, align: 'right', numeric: true },
  { key: 'avg_rating', label: 'Avg', sortable: true, align: 'right', numeric: true },
  {
    key: 'p50_rating',
    label: 'P50',
    sortable: true,
    align: 'right',
    numeric: true,
    format: (v) => formatRating(v),
  },
]

async function loadTournaments() {
  tournamentsLoading.value = true
  tournamentsError.value = ''

  try {
    const [tournamentRows, eventRows] = await Promise.all([fetchTournaments(), fetchEvents()])
    tournaments.value = Array.isArray(tournamentRows) ? tournamentRows : []
    events.value = Array.isArray(eventRows) ? eventRows : []
    const requested = String(route.query.tournament || '')
    if (requested && tournaments.value.some((row) => String(row.tournament_id) === requested)) {
      selectedTournament.value = requested
    }
    const visible = visibleTournaments.value
    if (!selectedTournament.value && visible.length) {
      selectedTournament.value = String(visible[0].tournament_id)
    }
  } catch (error) {
    tournaments.value = []
    tournamentsError.value = errorMessage(error, 'Failed to load tournaments')
  } finally {
    tournamentsLoading.value = false
  }
}

function loadTournamentData(tournamentId) {
  return Promise.all([
    matchQuery.loadMatches({ page: 1, pageSize: 12, tournamentId }),
    ratingQuery.loadLeaderboard(tournamentId, { className: classFilter.value, limit: 50, force: true }),
  ])
}

onMounted(async () => {
  await loadTournaments()
  await Promise.all([
    ratingQuery.loadBenchmarks({ force: true }),
    selectedTournament.value ? loadTournamentData(selectedTournament.value) : null,
  ])
})

watch(selectedTournament, async (tournamentId, previous) => {
  // The initial selection is loaded by onMounted.
  if (!tournamentId || !previous) return
  await loadTournamentData(tournamentId)
})

watch(selectedEvent, () => {
  const visible = visibleTournaments.value
  if (!visible.some((row) => String(row.tournament_id) === selectedTournament.value)) {
    selectedTournament.value = visible.length ? String(visible[0].tournament_id) : ''
  }
})

watch(classFilter, async () => {
  if (!selectedTournament.value) return
  await ratingQuery.loadLeaderboard(selectedTournament.value, {
    className: classFilter.value,
    limit: 50,
    force: true,
  })
})
</script>

<template>
  <div class="space-y-3">
    <h1 class="sr-only">Tournament overview</h1>

    <div v-if="tournamentsLoading" aria-busy="true" aria-label="Loading tournaments">
      <SkeletonBlock :rows="1" height="h-9" />
    </div>

    <StateMessage v-else-if="tournamentsError" tone="error">{{ tournamentsError }}</StateMessage>

    <Panel v-else-if="!tournaments.length" title="Tournaments">
      <StateMessage>
        No tournaments projected yet.
        <RouterLink v-if="canAdmin" class="data-link font-semibold text-blu" :to="{ name: 'admin-tournaments' }">
          Create one in Admin → Tournaments.
        </RouterLink>
        <template v-else>Check back once an admin has ingested logs.</template>
      </StateMessage>
    </Panel>

    <!-- Tournament tabs + event filter -->
    <div v-else class="flex flex-wrap items-center gap-2" data-test="tournament-tabs">
      <label v-if="events.length" class="sr-only" for="event-filter">Event</label>
      <select
        v-if="events.length"
        id="event-filter"
        v-model="selectedEvent"
        class="field w-auto py-1 text-xs"
      >
        <option value="">All events</option>
        <option v-for="event in events" :key="event.event_id" :value="String(event.event_id)">
          {{ event.name }}
        </option>
      </select>
      <button
        v-for="tournament in visibleTournaments"
        :key="tournament.tournament_id"
        type="button"
        class="tab"
        :class="{ 'tab-active': String(tournament.tournament_id) === selectedTournament }"
        :aria-pressed="String(tournament.tournament_id) === selectedTournament"
        @click="selectedTournament = String(tournament.tournament_id)"
      >
        {{ tournament.name }}
        <span class="ml-1.5 tabular-nums opacity-70">{{ Number(tournament.match_count) || 0 }}</span>
      </button>
      <StateMessage v-if="!visibleTournaments.length">No tournaments in this event yet.</StateMessage>
    </div>

    <div class="grid gap-3 lg:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[280px_minmax(0,1fr)_280px]">
      <!-- Left: recent results -->
      <Panel title="Recent results" flush class="order-2 lg:order-1">
        <template #actions>
          <RouterLink class="data-link text-xs text-ink-muted" to="/match">All results ›</RouterLink>
        </template>
        <StateMessage v-if="matchesError" tone="error" class="m-3">{{ matchesError }}</StateMessage>
        <MatchResultList
          v-else
          :matches="selectedTournament ? matches : []"
          :loading="matchesLoading"
          compact
          empty-message="No matches projected yet."
        />
      </Panel>

      <!-- Centre: leaderboard -->
      <Panel flush class="order-1 lg:order-2">
        <template #title>
          {{ selectedTournamentMeta ? `${selectedTournamentMeta.name} — leaderboard` : 'Leaderboard' }}
        </template>
        <PlayerLeaderboard
          v-model:class-filter="classFilter"
          :rows="selectedTournament ? leaderboard : []"
          :loading="leaderboardLoading"
          :error="leaderboardError"
          :empty-message="selectedTournament ? 'No players rated for this filter yet.' : 'Select a tournament.'"
        />
      </Panel>

      <!-- Right: tournament facts + benchmarks -->
      <div class="order-3 space-y-3 lg:col-span-2 xl:col-span-1">
        <Panel v-if="selectedTournamentMeta" title="Tournament">
          <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
            <dt class="text-ink-muted">Name</dt>
            <dd class="font-semibold">{{ selectedTournamentMeta.name }}</dd>
            <template v-if="selectedEventName">
              <dt class="text-ink-muted">Event</dt>
              <dd>
                <RouterLink class="data-link" :to="{ name: 'event', params: { eventId: selectedTournamentMeta.event_id } }">
                  {{ selectedEventName }}
                </RouterLink>
              </dd>
            </template>
            <dt class="text-ink-muted">Matches</dt>
            <dd class="tabular-nums">{{ Number(selectedTournamentMeta.match_count) || 0 }}</dd>
            <dt class="text-ink-muted">Started</dt>
            <dd>{{ formatDate(selectedTournamentMeta.started_at) }}</dd>
          </dl>
        </Panel>

        <Panel title="Class benchmarks" flush>
          <StateMessage v-if="benchmarksError" tone="error" class="m-3">{{ benchmarksError }}</StateMessage>
          <DataGrid
            v-else
            :rows="benchmarks"
            :columns="benchmarkColumns"
            :row-key="(row) => row.class_id ?? row.class_name"
            :loading="benchmarksLoading"
            empty-message="No class benchmarks yet."
            default-sort-key="avg_rating"
            fit-container
          >
            <template #cell-class_name="{ value }">
              <span class="capitalize">{{ value }}</span>
            </template>
            <template #cell-avg_rating="{ row }">
              <span class="rating-chip" :class="`tone-${ratingTone(row.avg_rating)}`">
                {{ formatRating(row.avg_rating, 2) }}
              </span>
            </template>
          </DataGrid>
        </Panel>
      </div>
    </div>
  </div>
</template>
