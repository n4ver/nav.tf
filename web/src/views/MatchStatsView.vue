<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import MatchSummaryCard from '../components/MatchSummaryCard.vue'
import { useMatchQueryStore } from '../stores/matchQuery'
import { formatRating, ratingTone } from '../utils/rating'
import { formatPlayerLabel } from '../utils/steam'

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

const activeMatchId = computed(() => {
  const raw = route.params.matchId
  return raw ? String(raw) : ''
})

function matchPath(matchId) {
  return `/match/${encodeURIComponent(String(matchId))}`
}

function playerPath(steamId) {
  return `/player/${encodeURIComponent(String(steamId))}`
}

function formatDuration(seconds) {
  const total = Number(seconds) || 0
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}m ${String(secs).padStart(2, '0')}s`
}

function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

function classesLabel(classesPlayed) {
  if (!Array.isArray(classesPlayed) || !classesPlayed.length) return '—'
  return classesPlayed.join(', ')
}

function sortByRatingDesc(players) {
  return [...players].sort((a, b) => (Number(b.rating) || 0) - (Number(a.rating) || 0))
}

const bluPlayers = computed(() =>
  sortByRatingDesc(matchPlayers.value.filter((p) => String(p.team || '').toLowerCase() === 'blu')),
)

const redPlayers = computed(() =>
  sortByRatingDesc(matchPlayers.value.filter((p) => String(p.team || '').toLowerCase() === 'red')),
)

const otherPlayers = computed(() =>
  sortByRatingDesc(
    matchPlayers.value.filter((p) => {
      const team = String(p.team || '').toLowerCase()
      return team !== 'blu' && team !== 'red'
    }),
  ),
)

const teamSections = computed(() => {
  const sections = []
  if (bluPlayers.value.length) {
    sections.push({ key: 'blu', title: 'Blu', players: bluPlayers.value })
  }
  if (redPlayers.value.length) {
    sections.push({ key: 'red', title: 'Red', players: redPlayers.value })
  }
  if (otherPlayers.value.length) {
    sections.push({ key: 'other', title: 'Other', players: otherPlayers.value })
  }
  return sections
})

async function goToPage(nextPage) {
  const safePage = Math.max(1, Number(nextPage) || 1)
  if (safePage === matchesPage.value) {
    return
  }

  await router.replace({
    name: 'match-stats',
    params: activeMatchId.value ? { matchId: activeMatchId.value } : {},
    query: { ...route.query, page: String(safePage) },
  })
}

async function openMatch(matchId) {
  await router.push({
    name: 'match-stats',
    params: { matchId: String(matchId) },
    query: route.query,
  })
}

watch(
  () => route.query.page,
  async (nextPage) => {
    const parsed = Math.max(1, Number(nextPage) || 1)
    if (parsed !== matchesPage.value || !matches.value.length) {
      await matchQuery.loadMatches({ page: parsed })
    }
  },
)

watch(
  () => route.params.matchId,
  async (nextId) => {
    if (!nextId) {
      matchQuery.clearMatchDetail()
      return
    }
    await matchQuery.loadMatchDetail(String(nextId))
  },
)

onMounted(async () => {
  const page = Math.max(1, Number(route.query.page) || 1)
  await matchQuery.loadMatches({ page })
  if (route.params.matchId) {
    await matchQuery.loadMatchDetail(String(route.params.matchId))
  }
})
</script>

<template>
  <div class="page-wrap">
    <header class="hero">
      <p class="eyebrow">TF2 analytics dashboard</p>
      <h1>Match Dashboard</h1>
      <p>Browse matches and player ratings. Log uploads are available to admins.</p>
    </header>

    <main class="content-grid space-y-4">
      <section class="panel">
        <div class="panel-head">
          <h2>Match details</h2>
          <p v-if="activeMatchId" class="status-msg mono text-sm">{{ activeMatchId }}</p>
        </div>

        <p v-if="!activeMatchId" class="status-msg">
          Select a match from the list or upload a log to view details.
        </p>
        <p v-if="matchDetailError" class="error-msg">{{ matchDetailError }}</p>

        <!-- Skeleton while Query service materializes / loads -->
        <div v-if="matchDetailLoading" class="space-y-4" aria-busy="true" aria-label="Loading match details">
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div v-for="n in 4" :key="n" class="h-16 animate-pulse rounded-lg bg-gray-200" />
          </div>
          <div class="space-y-2">
            <div v-for="n in 5" :key="`row-${n}`" class="h-10 animate-pulse rounded bg-gray-200" />
          </div>
        </div>

        <div v-else-if="matchSummary" class="log-grid">
          <MatchSummaryCard
            :summary="matchSummary"
            :format-duration="formatDuration"
            :format-date="formatDate"
          />
          <div>
            <h3>Team breakdown</h3>
            <template v-if="teamSections.length">
              <div
                v-for="section in teamSections"
                :key="section.key"
                class="team-section"
                :class="`team-${section.key}`"
              >
                <h4>{{ section.title }}</h4>
                <table>
                  <thead>
                    <tr>
                      <th>Player</th>
                      <th>Classes</th>
                      <th>K/D/A</th>
                      <th>DPM</th>
                      <th>Healing</th>
                      <th>Rating</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="entry in section.players" :key="`${entry.steam_id}-${entry.team}`">
                      <td>
                        <RouterLink class="inline-link" :to="playerPath(entry.steam_id)">
                          {{ formatPlayerLabel(entry) }}
                        </RouterLink>
                      </td>
                      <td>{{ classesLabel(entry.classes_played) }}</td>
                      <td>{{ entry.kills }}/{{ entry.deaths }}/{{ entry.assists }}</td>
                      <td>{{ entry.damage_per_minute }}</td>
                      <td>{{ entry.healing_done }}</td>
                      <td>
                        <span class="rating-chip" :class="`tone-${ratingTone(entry.rating)}`">
                          {{ formatRating(entry.rating) }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
            <p v-else class="status-msg">No player rows for this match yet.</p>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>All matches</h2>
          <p class="status-msg">
            Page {{ matchesPage }} · {{ matches.length }} shown
            <span v-if="matchesHasMore"> · more available</span>
          </p>
        </div>

        <p v-if="matchesError" class="error-msg">{{ matchesError }}</p>

        <div v-if="matchesLoading" class="space-y-2" aria-busy="true" aria-label="Loading matches">
          <div v-for="n in 6" :key="n" class="h-10 animate-pulse rounded bg-gray-200" />
        </div>

        <table v-else-if="matches.length">
          <thead>
            <tr>
              <th>Match ID</th>
              <th>Map</th>
              <th>Winner</th>
              <th>Duration</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="match in matches"
              :key="match.match_id"
              class="cursor-pointer"
              :class="{ 'bg-sky-50': String(match.match_id) === activeMatchId }"
              @click="openMatch(match.match_id)"
            >
              <td>
                <RouterLink class="inline-link mono" :to="matchPath(match.match_id)">
                  {{ match.match_id }}
                </RouterLink>
              </td>
              <td>{{ match.map_name }}</td>
              <td>{{ match.winning_team }}</td>
              <td>{{ formatDuration(match.duration_seconds) }}</td>
              <td>{{ formatDate(match.date_played) }}</td>
            </tr>
          </tbody>
        </table>

        <p v-else-if="!matchesError" class="status-msg">No matches found.</p>

        <div class="leaderboard-pagination">
          <button
            type="button"
            :disabled="matchesLoading || matchesPage <= 1"
            @click="goToPage(matchesPage - 1)"
          >
            Previous
          </button>
          <span>Page {{ matchesPage }}</span>
          <button
            type="button"
            :disabled="matchesLoading || !matchesHasMore"
            @click="goToPage(matchesPage + 1)"
          >
            Next
          </button>
        </div>
      </section>
    </main>
  </div>
</template>
