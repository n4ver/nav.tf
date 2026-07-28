<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { fetchQueryHealth, fetchTournaments, getQueryBaseUrl } from '../api'
import { useCan } from '../composables/useCan'
import { useMatchQueryStore } from '../stores/matchQuery'
import { useRatingQueryStore } from '../stores/ratingQuery'
import { formatRating, ratingTone } from '../utils/rating'
import { formatPlayerLabel } from '../utils/steam'

const apiBaseUrl = getQueryBaseUrl()
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

const health = ref(null)
const healthError = ref('')

const tournaments = ref([])
const tournamentsLoading = ref(false)
const tournamentsError = ref('')
const selectedTournament = ref('')
const classFilter = ref('')

function tournamentLabel(tournament) {
  const matchCount = Number(tournament.match_count) || 0
  const suffix = matchCount === 1 ? 'match' : 'matches'
  return `${tournament.name} — ${matchCount} ${suffix}`
}

function selectTournament(tournament) {
  selectedTournament.value = String(tournament.tournament_id)
}

function matchPath(matchId) {
  return `/match/${encodeURIComponent(String(matchId))}`
}

function playerPath(steamId) {
  return `/player/${encodeURIComponent(String(steamId))}`
}

function formatDuration(seconds) {
  const total = Number(seconds) || 0
  const mins = Math.floor(total / 60)
  return `${mins}m`
}

function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

const selectedTournamentMeta = computed(() =>
  tournaments.value.find((t) => String(t.tournament_id) === selectedTournament.value) || null,
)

async function loadTournaments() {
  tournamentsLoading.value = true
  tournamentsError.value = ''

  try {
    tournaments.value = await fetchTournaments()
    if (!selectedTournament.value && tournaments.value.length) {
      selectedTournament.value = String(tournaments.value[0].tournament_id)
    }
    if (!tournaments.value.length) {
      tournamentsError.value = 'No tournaments projected yet. Upload a log to seed data.'
    }
  } catch (error) {
    tournaments.value = []
    tournamentsError.value = error instanceof Error ? error.message : 'Failed to load tournaments'
  } finally {
    tournamentsLoading.value = false
  }
}

async function loadRatingViews({ force = false } = {}) {
  const tasks = [ratingQuery.loadBenchmarks({ force })]
  if (selectedTournament.value) {
    tasks.push(
      ratingQuery.loadLeaderboard(selectedTournament.value, {
        className: classFilter.value,
        limit: 25,
        force,
      }),
    )
  }
  await Promise.all(tasks)
}

async function loadHealth() {
  healthError.value = ''
  try {
    health.value = await fetchQueryHealth()
  } catch (error) {
    health.value = null
    healthError.value = error instanceof Error ? error.message : 'Failed to check API health'
  }
}

onMounted(async () => {
  await loadHealth()
  await loadTournaments()
  if (selectedTournament.value) {
    await Promise.all([
      matchQuery.loadMatches({
        page: 1,
        pageSize: 10,
        tournamentId: selectedTournament.value,
      }),
      loadRatingViews({ force: true }),
    ])
  } else {
    await ratingQuery.loadBenchmarks({ force: true })
  }
})

watch(selectedTournament, async (tournamentId) => {
  if (!tournamentId) {
    return
  }
  await Promise.all([
    matchQuery.loadMatches({ page: 1, pageSize: 10, tournamentId }),
    ratingQuery.loadLeaderboard(tournamentId, {
      className: classFilter.value,
      limit: 25,
      force: true,
    }),
  ])
})

watch(classFilter, async () => {
  if (!selectedTournament.value) {
    return
  }
  await ratingQuery.loadLeaderboard(selectedTournament.value, {
    className: classFilter.value,
    limit: 25,
    force: true,
  })
})
</script>

<template>
  <div class="page-wrap">
    <header class="hero">
      <p class="eyebrow">TF2 analytics dashboard</p>
      <h1>Tournament Dashboard</h1>
      <p>
        Standings use the Query-side RatingService (0–2 band, 1.0 ≈ class average) at
        <code>{{ apiBaseUrl }}</code>.
      </p>
      <p v-if="canAdmin">
        <RouterLink class="inline-link" to="/admin/dashboard">Edit tournaments &amp; upload logs</RouterLink>
      </p>
      <div class="health-chip" :class="{ bad: healthError }">
        <strong>API health:</strong>
        <span v-if="health">{{ health.status }}{{ health.side ? ` (${health.side})` : '' }}</span>
        <span v-else-if="healthError">Unavailable</span>
        <span v-else>Checking...</span>
      </div>
      <p v-if="healthError" class="error-msg">{{ healthError }}</p>
    </header>

    <main class="content-grid">
      <section class="panel">
        <div v-if="tournaments.length" class="tournament-index">
          <button
            v-for="tournament in tournaments"
            :key="tournament.tournament_id"
            type="button"
            class="tournament-card"
            :class="{ active: String(tournament.tournament_id) === selectedTournament }"
            @click="selectTournament(tournament)"
          >
            <span class="tournament-card-title">{{ tournament.name }}</span>
            <span class="tournament-card-meta">{{ tournament.slug }}</span>
            <span class="tournament-card-meta">{{ Number(tournament.match_count) || 0 }} matches</span>
          </button>
        </div>

        <div class="panel-head">
          <h2>Tournament</h2>
          <form
            @submit.prevent="
              async () => {
                await loadTournaments()
                await loadRatingViews({ force: true })
              }
            "
          >
            <label>
              Tournament
              <select v-model="selectedTournament" :disabled="tournamentsLoading || !tournaments.length">
                <option
                  v-for="tournament in tournaments"
                  :key="tournament.tournament_id"
                  :value="String(tournament.tournament_id)"
                >
                  {{ tournamentLabel(tournament) }}
                </option>
              </select>
            </label>
            <button type="submit" :disabled="tournamentsLoading">Refresh</button>
          </form>
        </div>

        <p v-if="tournamentsError" class="error-msg">{{ tournamentsError }}</p>
        <p v-else-if="tournamentsLoading" class="status-msg">Loading tournament index...</p>

        <div v-if="tournamentsLoading" class="mt-3 grid gap-2 sm:grid-cols-3">
          <div v-for="n in 3" :key="n" class="h-24 animate-pulse rounded-xl bg-gray-200" />
        </div>

        <div class="split" v-if="!tournamentsLoading">
          <article>
            <h3>Selected tournament</h3>
            <ul v-if="selectedTournamentMeta" class="stat-list">
              <li><strong>Name:</strong> {{ selectedTournamentMeta.name }}</li>
              <li><strong>Slug:</strong> {{ selectedTournamentMeta.slug }}</li>
              <li><strong>Matches:</strong> {{ selectedTournamentMeta.match_count }}</li>
              <li>
                <strong>Started:</strong>
                {{ formatDate(selectedTournamentMeta.started_at) }}
              </li>
            </ul>
            <p v-else class="status-msg">
              Upload a log from the Match Dashboard to project tournament summaries.
            </p>
          </article>

          <article>
            <h3>Recent matches</h3>
            <p v-if="matchesError" class="error-msg">{{ matchesError }}</p>
            <div v-if="matchesLoading" class="space-y-2" aria-busy="true">
              <div v-for="n in 4" :key="n" class="h-10 animate-pulse rounded bg-gray-200" />
            </div>
            <table v-else-if="matches.length">
              <thead>
                <tr>
                  <th>Match</th>
                  <th>Map</th>
                  <th>Winner</th>
                  <th>Duration</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="match in matches" :key="match.match_id">
                  <td>
                    <RouterLink class="inline-link mono" :to="matchPath(match.match_id)">
                      {{ String(match.match_id).slice(0, 8) }}…
                    </RouterLink>
                  </td>
                  <td>{{ match.map_name }}</td>
                  <td>{{ match.winning_team }}</td>
                  <td>{{ formatDuration(match.duration_seconds) }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="status-msg">No matches projected yet.</p>
          </article>
        </div>

        <div class="mt-4" v-if="selectedTournament">
          <div class="panel-head">
            <h3>Rating leaderboard</h3>
            <label>
              Class filter
              <select v-model="classFilter">
                <option value="">All classes</option>
                <option value="scout">scout</option>
                <option value="soldier">soldier</option>
                <option value="pyro">pyro</option>
                <option value="demoman">demoman</option>
                <option value="heavyweapons">heavyweapons</option>
                <option value="engineer">engineer</option>
                <option value="medic">medic</option>
                <option value="sniper">sniper</option>
                <option value="spy">spy</option>
              </select>
            </label>
          </div>

          <p v-if="leaderboardError" class="error-msg">{{ leaderboardError }}</p>
          <div v-if="leaderboardLoading" class="space-y-2" aria-busy="true">
            <div v-for="n in 5" :key="n" class="h-10 animate-pulse rounded bg-gray-200" />
          </div>
          <table v-else-if="leaderboard.length">
            <thead>
              <tr>
                <th>#</th>
                <th>Player</th>
                <th>Class</th>
                <th>Matches</th>
                <th>K/D/A</th>
                <th>Avg DPM</th>
                <th>Rating</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(entry, index) in leaderboard" :key="entry.steam_id">
                <td>{{ index + 1 }}</td>
                <td>
                  <RouterLink class="inline-link" :to="playerPath(entry.steam_id)">
                    {{ formatPlayerLabel(entry) }}
                  </RouterLink>
                </td>
                <td>{{ entry.primary_class }}</td>
                <td>{{ entry.matches_played }}</td>
                <td>{{ entry.total_kills }}/{{ entry.total_deaths }}/{{ entry.total_assists }}</td>
                <td>{{ entry.average_damage_per_minute }}</td>
                <td>
                  <span class="rating-chip" :class="`tone-${ratingTone(entry.average_rating)}`">
                    {{ formatRating(entry.average_rating) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="status-msg">No leaderboard rows yet for this tournament.</p>
        </div>

        <div class="mt-4">
          <div class="panel-head">
            <h3>Class rating benchmarks</h3>
            <p class="status-msg">Baselines rebuilt after each MatchParsed projection.</p>
          </div>
          <p v-if="benchmarksError" class="error-msg">{{ benchmarksError }}</p>
          <div v-if="benchmarksLoading" class="space-y-2" aria-busy="true">
            <div v-for="n in 4" :key="n" class="h-10 animate-pulse rounded bg-gray-200" />
          </div>
          <table v-else-if="benchmarks.length">
            <thead>
              <tr>
                <th>Class</th>
                <th>Samples</th>
                <th>Avg</th>
                <th>P50</th>
                <th>Min</th>
                <th>Max</th>
                <th>Std</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in benchmarks" :key="row.class_id ?? row.class_name">
                <td>{{ row.class_name }}</td>
                <td>{{ row.sample_size }}</td>
                <td>
                  <span class="rating-chip" :class="`tone-${ratingTone(row.avg_rating)}`">
                    {{ formatRating(row.avg_rating) }}
                  </span>
                </td>
                <td>{{ formatRating(row.p50_rating) }}</td>
                <td>{{ formatRating(row.min_rating) }}</td>
                <td>{{ formatRating(row.max_rating) }}</td>
                <td>{{ formatRating(row.std_rating) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="status-msg">No class benchmarks yet. Ingest a match to rebuild ratings.</p>
        </div>
      </section>
    </main>
  </div>
</template>
