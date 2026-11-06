<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import PlayerCareerSummary from '../components/stats/PlayerCareerSummary.vue'
import DataGrid from '../components/ui/DataGrid.vue'
import Panel from '../components/ui/Panel.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import StateMessage from '../components/ui/StateMessage.vue'
import { usePlayerQueryStore } from '../stores/playerQuery'
import { classesLabel, formatDate, formatNumber, matchPath } from '../utils/format'
import { formatRating, ratingTone } from '../utils/rating'
import { convertToSteamID64 } from '../utils/steam'

const route = useRoute()
const router = useRouter()
const playerQuery = usePlayerQueryStore()
const { stats, loading, error } = storeToRefs(playerQuery)

function decodeSteamId(value) {
  try {
    return decodeURIComponent(String(value || ''))
  } catch {
    return String(value || '')
  }
}

const steamId = ref(decodeSteamId(route.params.steamId))
const hasRouteSteamId = computed(() => Boolean(route.params.steamId))

const classColumns = [
  { key: 'class_name', label: 'Class', sortable: true },
  { key: 'matches_played', label: 'Maps', sortable: true, align: 'right', numeric: true, hideBelow: 'md' },
  {
    key: 'kd',
    label: 'K-D',
    sortable: true,
    align: 'right',
    numeric: true,
    value: (row) => `${row.total_kills}-${row.total_deaths}`,
    sortValue: (a, b) => (Number(a.total_kills) || 0) - (Number(b.total_kills) || 0),
  },
  { key: 'total_assists', label: 'A', sortable: true, align: 'right', numeric: true, hideBelow: 'md' },
  {
    key: 'average_damage_per_minute',
    label: 'DPM',
    sortable: true,
    align: 'right',
    numeric: true,
    format: (v) => formatNumber(v, 1),
  },
  { key: 'total_healing_done', label: 'Heals', sortable: true, align: 'right', numeric: true, hideBelow: 'md' },
  { key: 'average_rating', label: 'Rating', sortable: true, align: 'right', numeric: true },
]

const recentColumns = [
  {
    key: 'date_played',
    label: 'Date',
    sortable: true,
    format: (v) => formatDate(v),
  },
  { key: 'map_name', label: 'Map', sortable: true, hideBelow: 'md' },
  {
    key: 'team',
    hideBelow: 'md',
    label: 'Team',
    sortable: true,
    format: (v) => String(v || '').toUpperCase(),
  },
  {
    key: 'classes',
    hideBelow: 'md',
    label: 'Classes',
    sortable: true,
    value: (row) => classesLabel(row.classes_played),
  },
  {
    key: 'kd',
    label: 'K-D',
    sortable: true,
    align: 'right',
    numeric: true,
    value: (row) => `${row.kills}-${row.deaths}`,
    sortValue: (a, b) => (Number(a.kills) || 0) - (Number(b.kills) || 0),
  },
  { key: 'assists', label: 'A', sortable: true, align: 'right', numeric: true, hideBelow: 'md' },
  {
    key: 'damage_per_minute',
    hideBelow: 'md',
    label: 'DPM',
    sortable: true,
    align: 'right',
    numeric: true,
    format: (v) => formatNumber(v, 1),
  },
  { key: 'rating', label: 'Rating', sortable: true, align: 'right', numeric: true },
]

async function submitAndLoad() {
  const raw = steamId.value.trim()
  if (!raw) {
    return
  }
  const query = convertToSteamID64(raw) || raw

  if (String(route.params.steamId || '') === query) {
    // Same route: the param watcher will not fire, so refresh explicitly.
    await playerQuery.loadPlayerStats(query, { force: true })
    return
  }
  // The route watcher performs the load.
  await router.push({ name: 'player-stats', params: { steamId: query } })
}

watch(
  () => route.params.steamId,
  async (nextSteamId) => {
    if (!nextSteamId) {
      steamId.value = ''
      playerQuery.clear()
      return
    }
    steamId.value = decodeSteamId(nextSteamId)
    await playerQuery.loadPlayerStats(steamId.value)
  },
)

onMounted(async () => {
  if (route.params.steamId) {
    await playerQuery.loadPlayerStats(decodeSteamId(route.params.steamId))
  } else {
    playerQuery.clear()
  }
})
</script>

<template>
  <div class="space-y-3">
    <!-- Lookup bar: always available, compact -->
    <form
      class="flex flex-wrap items-center gap-2 rounded-sm border border-line bg-surface-800 px-3 py-2"
      role="search"
      @submit.prevent="submitAndLoad"
    >
      <label for="player-lookup" class="text-sm font-semibold text-ink">Player lookup</label>
      <input
        id="player-lookup"
        v-model.trim="steamId"
        placeholder="SteamID64, STEAM_0:1:123 or [U:1:123]"
        required
        class="field w-auto min-w-[16rem] flex-1 sm:flex-none"
      />
      <button type="submit" :disabled="loading" class="btn-primary">Look up</button>
      <span class="text-xs text-ink-muted">Search by name with the bar at the top of the page.</span>
    </form>

    <div v-if="loading" class="space-y-3" aria-busy="true" aria-label="Loading player stats">
      <SkeletonBlock :rows="1" height="h-28" />
      <SkeletonBlock :rows="6" height="h-8" />
    </div>

    <StateMessage v-else-if="error" tone="error">{{ error }}</StateMessage>

    <Panel v-else-if="!hasRouteSteamId" title="Players">
      <h1 class="sr-only">Players</h1>
      <StateMessage>
        Enter a SteamID above, or use the header search to find a player by name. Player names on
        any leaderboard or scoreboard also link here.
      </StateMessage>
    </Panel>

    <template v-else-if="stats">
      <PlayerCareerSummary :stats="stats" />

      <StateMessage v-if="stats.matches_played === 0">
        No projected stats yet for this SteamID. Upload a log that includes this player.
      </StateMessage>

      <div v-else class="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Panel title="By class" flush>
          <DataGrid
            :rows="stats.class_breakdown || []"
            :columns="classColumns"
            row-key="class_name"
            default-sort-key="matches_played"
            empty-message="No class breakdown yet."
            fit-container
          >
            <template #cell-class_name="{ value }">
              <span class="font-semibold capitalize">{{ value }}</span>
            </template>
            <template #cell-average_rating="{ row }">
              <span class="rating-chip" :class="`tone-${ratingTone(row.average_rating)}`">
                {{ formatRating(row.average_rating, 2) }}
              </span>
            </template>
          </DataGrid>
        </Panel>

        <Panel title="Recent matches" flush>
          <DataGrid
            :rows="stats.recent_matches || []"
            :columns="recentColumns"
            row-key="match_id"
            default-sort-key="date_played"
            empty-message="No recent match history available yet."
          >
            <template #cell-date_played="{ row }">
              <RouterLink class="data-link text-blu" :to="matchPath(row.match_id)">
                {{ formatDate(row.date_played) }}
              </RouterLink>
            </template>
            <template #cell-team="{ value }">
              <span
                class="font-bold uppercase"
                :class="{
                  'text-blu': String(value).toLowerCase() === 'blu',
                  'text-red': String(value).toLowerCase() === 'red',
                }"
              >
                {{ String(value || '').toUpperCase() }}
              </span>
            </template>
            <template #cell-rating="{ row }">
              <span class="rating-chip" :class="`tone-${ratingTone(row.rating)}`">
                {{ formatRating(row.rating, 2) }}
              </span>
            </template>
          </DataGrid>
        </Panel>
      </div>
    </template>

    <StateMessage v-else>No player data loaded.</StateMessage>
  </div>
</template>
