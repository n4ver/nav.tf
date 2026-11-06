<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { fetchTournaments } from '../api'
import MatchResultList from '../components/match/MatchResultList.vue'
import MatchSummaryCard from '../components/match/MatchSummaryCard.vue'
import DataGrid from '../components/ui/DataGrid.vue'
import Panel from '../components/ui/Panel.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import StateMessage from '../components/ui/StateMessage.vue'
import { useMatchQueryStore } from '../stores/matchQuery'
import { classesLabel, formatAccuracy, formatDuration, formatNumber, playerPath } from '../utils/format'
import { formatRating, ratingTone } from '../utils/rating'
import { formatPlayerLabel } from '../utils/steam'

const PAGE_SIZE = 30

const route = useRoute()
const router = useRouter()
const matchQuery = useMatchQueryStore()

const {
  matches,
  matchesPage,
  matchesHasMore,
  matchesLoading,
  matchesError,
  matchSummary,
  matchPlayers,
  matchDetailLoading,
  matchDetailError,
} = storeToRefs(matchQuery)

const activeMatchId = computed(() => (route.params.matchId ? String(route.params.matchId) : ''))

/* ---- Tournament names (results rows + match header) --------------------- */

const tournamentNames = ref({})

async function loadTournamentNames() {
  try {
    const rows = await fetchTournaments()
    tournamentNames.value = Object.fromEntries(
      (Array.isArray(rows) ? rows : []).map((row) => [row.tournament_id, row.name]),
    )
  } catch {
    // Names are decoration; the pages work without them.
    tournamentNames.value = {}
  }
}

/* ---- Match page: scoreboards ------------------------------------------- */

const TEAMS = [
  { key: 'blu', title: 'BLU' },
  { key: 'red', title: 'RED' },
  { key: 'other', title: 'Other' },
]

function teamOf(player) {
  const team = String(player.team || '').toLowerCase()
  return team === 'blu' || team === 'red' ? team : 'other'
}

const teamSections = computed(() =>
  TEAMS.map((team) => {
    const players = matchPlayers.value
      .filter((player) => teamOf(player) === team.key)
      .sort((a, b) => (Number(b.rating) || 0) - (Number(a.rating) || 0))
    const kills = players.reduce((sum, p) => sum + (Number(p.kills) || 0), 0)
    const deaths = players.reduce((sum, p) => sum + (Number(p.deaths) || 0), 0)
    return { ...team, players, kills, deaths }
  }).filter((section) => section.players.length),
)

/** Class-stats breakdowns start collapsed per team. */
const classStatsOpen = reactive({ blu: false, red: false, other: false })

function classStatRowsFor(players) {
  return players.flatMap((player) =>
    (player.class_stats || []).map((snap) => ({
      ...snap,
      steam_id: player.steam_id,
      display_name: player.display_name,
      row_id: `${player.steam_id}-${snap.class_id}-${snap.class_name}`,
    })),
  )
}

const OPTIONAL_STATS = [
  { key: 'ubers', label: 'Ubers' },
  { key: 'drops', label: 'Drops' },
  { key: 'captures', label: 'Caps' },
  { key: 'headshots', label: 'HS' },
  { key: 'backstabs', label: 'BS' },
  { key: 'airshots', label: 'Air' },
]

/** Hide niche columns (ubers, airshots…) when nobody in the match recorded any. */
const playerColumns = computed(() => {
  const players = matchPlayers.value
  const optional = OPTIONAL_STATS.filter((stat) =>
    players.some((player) => Number(player[stat.key]) > 0),
  ).map((stat) => ({ ...stat, sortable: true, align: 'right', numeric: true, hideBelow: 'md' }))

  return [
    { key: 'player', label: 'Player', sortable: true, truncate: true, value: (row) => formatPlayerLabel(row) },
    { key: 'classes', label: 'Class', sortable: true, value: (row) => classesLabel(row.classes_played), hideBelow: 'md' },
    { key: 'kills', label: 'K', sortable: true, align: 'right', numeric: true },
    { key: 'assists', label: 'A', sortable: true, align: 'right', numeric: true, hideBelow: 'md' },
    { key: 'deaths', label: 'D', sortable: true, align: 'right', numeric: true },
    {
      key: 'diff',
      label: '+/-',
      sortable: true,
      align: 'right',
      numeric: true,
      value: (row) => (Number(row.kills) || 0) - (Number(row.deaths) || 0),
    },
    {
      key: 'damage_per_minute',
      label: 'DPM',
      sortable: true,
      align: 'right',
      numeric: true,
      format: (v) => formatNumber(v, 0),
    },
    { key: 'damage_received', label: 'DT', sortable: true, align: 'right', numeric: true, hideBelow: 'md' },
    { key: 'heals_received', label: 'HR', sortable: true, align: 'right', numeric: true, hideBelow: 'md' },
    { key: 'healing_done', label: 'Heals', sortable: true, align: 'right', numeric: true, hideBelow: 'md' },
    ...optional,
    { key: 'rating', label: 'Rating', sortable: true, align: 'right', numeric: true },
  ]
})

const classStatColumns = [
  { key: 'player', label: 'Player', sortable: true, truncate: true, value: (row) => formatPlayerLabel(row) },
  { key: 'class_name', label: 'Class', sortable: true },
  {
    key: 'playtime_seconds',
    hideBelow: 'md',
    label: 'Time',
    sortable: true,
    align: 'right',
    numeric: true,
    format: (v) => formatDuration(v),
  },
  {
    key: 'kda',
    label: 'K/A/D',
    sortable: true,
    align: 'right',
    numeric: true,
    value: (row) => `${row.kills}/${row.assists}/${row.deaths}`,
    sortValue: (a, b) => (Number(a.kills) || 0) - (Number(b.kills) || 0),
  },
  { key: 'dpm', label: 'DPM', sortable: true, align: 'right', numeric: true },
  { key: 'damage_dealt', label: 'DMG', sortable: true, align: 'right', numeric: true, hideBelow: 'md' },
  { key: 'healing_done', label: 'Heals', sortable: true, align: 'right', numeric: true },
  {
    key: 'primary_accuracy',
    hideBelow: 'md',
    label: 'Acc',
    sortable: true,
    align: 'right',
    numeric: true,
    format: (v) => formatAccuracy(v),
  },
  { key: 'rating', label: 'Rating', sortable: true, align: 'right', numeric: true },
]

/* ---- Results page: pagination ------------------------------------------ */

async function goToPage(nextPage) {
  const safePage = Math.max(1, Number(nextPage) || 1)
  if (safePage === matchesPage.value) return
  await router.replace({ name: 'match-stats', query: { ...route.query, page: String(safePage) } })
}

function loadResultsPage() {
  const page = Math.max(1, Number(route.query.page) || 1)
  return matchQuery.loadMatches({ page, pageSize: PAGE_SIZE })
}

async function loadForRoute() {
  classStatsOpen.blu = false
  classStatsOpen.red = false
  classStatsOpen.other = false
  if (activeMatchId.value) {
    await matchQuery.loadMatchDetail(activeMatchId.value, { force: true })
  } else {
    matchQuery.clearMatchDetail()
    await loadResultsPage()
  }
}

watch(() => route.params.matchId, loadForRoute)

watch(
  () => route.query.page,
  async () => {
    if (!activeMatchId.value) await loadResultsPage()
  },
)

onMounted(async () => {
  await Promise.all([loadTournamentNames(), loadForRoute()])
})
</script>

<template>
  <!-- ===== Match page ===== -->
  <div v-if="activeMatchId" class="space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <RouterLink class="data-link text-sm text-ink-muted" :to="{ name: 'match-stats' }">‹ All results</RouterLink>
      <span class="font-mono text-xs text-ink-muted">{{ activeMatchId }}</span>
    </div>
    <h1 class="sr-only">Match {{ matchSummary?.map_name || activeMatchId }}</h1>

    <div v-if="matchDetailLoading" class="space-y-3" aria-busy="true" aria-label="Loading match details">
      <SkeletonBlock :rows="1" height="h-28" />
      <SkeletonBlock :rows="6" height="h-8" />
    </div>

    <StateMessage v-else-if="matchDetailError" tone="error">{{ matchDetailError }}</StateMessage>

    <template v-else-if="matchSummary">
      <MatchSummaryCard
        :summary="matchSummary"
        :tournament-name="tournamentNames[matchSummary.tournament_id] || ''"
      />

      <StateMessage v-if="!teamSections.length">No player rows for this match yet.</StateMessage>

      <Panel
        v-for="section in teamSections"
        :key="section.key"
        flush
        :data-test="`scoreboard-${section.key}`"
      >
        <template #title>
          <span :class="{ 'text-blu': section.key === 'blu', 'text-red': section.key === 'red' }">
            {{ section.title }}
          </span>
          <span class="ml-2 font-normal normal-case tracking-normal text-ink-muted">
            {{ section.players.length }} players · {{ section.kills }} kills · {{ section.deaths }} deaths
          </span>
        </template>
        <template #actions>
          <button
            v-if="classStatRowsFor(section.players).length"
            type="button"
            class="tab"
            :class="{ 'tab-active': classStatsOpen[section.key] }"
            :aria-expanded="classStatsOpen[section.key]"
            :aria-controls="`class-stats-${section.key}`"
            @click="classStatsOpen[section.key] = !classStatsOpen[section.key]"
          >
            Per-class stats
          </button>
        </template>

        <DataGrid
          :rows="section.players"
          :columns="playerColumns"
          :row-key="(row) => `${row.steam_id}-${row.team}`"
          default-sort-key="rating"
        >
          <template #cell-player="{ row }">
            <RouterLink class="data-link font-semibold" :to="playerPath(row.steam_id)">
              {{ formatPlayerLabel(row) }}
            </RouterLink>
          </template>
          <template #cell-diff="{ value }">
            <span :class="value > 0 ? 'text-ok' : value < 0 ? 'text-danger' : 'text-ink-muted'">
              {{ value > 0 ? `+${value}` : value }}
            </span>
          </template>
          <template #cell-rating="{ row }">
            <span class="rating-chip" :class="`tone-${ratingTone(row.rating)}`">
              {{ formatRating(row.rating, 2) }}
            </span>
          </template>
        </DataGrid>

        <div
          v-show="classStatsOpen[section.key]"
          :id="`class-stats-${section.key}`"
          class="border-t border-line"
        >
          <p class="bg-surface-900 px-3 py-1 text-xs font-bold uppercase tracking-wide text-ink-muted">
            {{ section.title }} per-class stats
          </p>
          <DataGrid
            :rows="classStatRowsFor(section.players)"
            :columns="classStatColumns"
            row-key="row_id"
            default-sort-key="dpm"
          >
            <template #cell-player="{ row }">
              <RouterLink class="data-link" :to="playerPath(row.steam_id)">
                {{ formatPlayerLabel(row) }}
              </RouterLink>
            </template>
            <template #cell-rating="{ row }">
              <span class="rating-chip" :class="`tone-${ratingTone(row.rating)}`">
                {{ formatRating(row.rating, 2) }}
              </span>
            </template>
          </DataGrid>
        </div>
      </Panel>
    </template>

    <StateMessage v-else>Match not found or not projected yet.</StateMessage>
  </div>

  <!-- ===== Results page ===== -->
  <div v-else class="space-y-3">
    <h1 class="text-lg font-bold">Results</h1>

    <StateMessage v-if="matchesError" tone="error">{{ matchesError }}</StateMessage>

    <Panel v-else flush>
      <template #title>All matches</template>
      <template #actions>
        <span class="text-xs text-ink-muted">Page {{ matchesPage }}</span>
      </template>
      <MatchResultList
        :matches="matches"
        :loading="matchesLoading"
        :tournament-names="tournamentNames"
        group-by-day
        empty-message="No matches found."
      />
      <nav
        class="flex items-center justify-between gap-3 border-t border-line bg-surface-900 px-3 py-2"
        aria-label="Results pages"
      >
        <button
          type="button"
          class="btn-ghost"
          :disabled="matchesLoading || matchesPage <= 1"
          @click="goToPage(matchesPage - 1)"
        >
          ‹ Newer
        </button>
        <span class="text-xs text-ink-muted">Page {{ matchesPage }}</span>
        <button
          type="button"
          class="btn-ghost"
          :disabled="matchesLoading || !matchesHasMore"
          @click="goToPage(matchesPage + 1)"
        >
          Older ›
        </button>
      </nav>
    </Panel>
  </div>
</template>
