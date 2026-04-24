<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchJson } from '../api'

const route = useRoute()
const router = useRouter()

const logId = ref(Number(route.params.logId) || 123456)
const logStats = ref(null)
const logLoading = ref(false)
const logError = ref('')

const matches = ref([])
const matchesTotal = ref(0)
const matchesPage = ref(1)
const matchesPageSize = 20
const matchesLoading = ref(false)
const matchesError = ref('')

function clampPage(page) {
  return Math.max(1, Number(page) || 1)
}

function logPath(nextLogId) {
  return `/match/${encodeURIComponent(String(nextLogId))}`
}

function formatTournamentName(match) {
  if (match.tournament?.name) {
    return `${match.tournament.name} (#${match.tournament_id})`
  }
  return `Tournament #${match.tournament_id}`
}

async function loadMatches() {
  matchesLoading.value = true
  matchesError.value = ''

  try {
    const offset = (matchesPage.value - 1) * matchesPageSize
    const payload = await fetchJson(`/matches?limit=${matchesPageSize}&offset=${offset}`)
    matches.value = Array.isArray(payload.items) ? payload.items : []
    matchesTotal.value = Number(payload.total) || 0
  } catch (error) {
    matches.value = []
    matchesTotal.value = 0
    matchesError.value = error instanceof Error ? error.message : 'Failed to load matches'
  } finally {
    matchesLoading.value = false
  }
}

const totalPages = () => Math.max(1, Math.ceil(matchesTotal.value / matchesPageSize))

async function goToPage(nextPage) {
  const safePage = Math.min(clampPage(nextPage), totalPages())
  if (safePage === matchesPage.value) {
    return
  }

  await router.replace({
    name: 'match-stats',
    params: route.params.logId ? { logId: String(route.params.logId) } : {},
    query: { ...route.query, page: String(safePage) },
  })
}

function playerPath(steamId) {
  return `/player/${encodeURIComponent(String(steamId))}`
}

async function loadLogStats() {
  logLoading.value = true
  logError.value = ''

  try {
    logStats.value = await fetchJson(`/logs/${logId.value}/stats`)
  } catch (error) {
    logStats.value = null
    logError.value = error instanceof Error ? error.message : 'Failed to load log stats'
  } finally {
    logLoading.value = false
  }
}

async function submitAndLoad() {
  await router.replace({
    name: 'match-stats',
    params: { logId: String(logId.value) },
    query: route.query,
  })
  await loadLogStats()
}

watch(
  () => route.query.page,
  async (nextPage) => {
    const parsed = clampPage(nextPage)
    if (parsed !== matchesPage.value) {
      matchesPage.value = parsed
      await loadMatches()
    }
  },
)

watch(
  () => route.params.logId,
  async (nextLogId) => {
    if (!nextLogId) {
      return
    }
    const parsed = Number(nextLogId)
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return
    }
    logId.value = parsed
    await loadLogStats()
  },
)

onMounted(async () => {
  matchesPage.value = clampPage(route.query.page)
  await loadMatches()

  if (route.params.logId) {
    await loadLogStats()
  }
})
</script>

<template>
  <div class="page-wrap">
    <header class="hero">
      <p class="eyebrow">TF2 analytics dashboard</p>
      <h1>Match Statistics</h1>
      <p>Look up a specific log and inspect detailed match metrics.</p>
    </header>

    <main class="content-grid">
      <section class="panel">
        <div class="panel-head">
          <h2>Log Stats</h2>
          <form @submit.prevent="submitAndLoad">
            <label>
              Log ID
              <input v-model.number="logId" type="number" min="1" required />
            </label>
            <button type="submit" :disabled="logLoading">Fetch</button>
          </form>
        </div>

        <p v-if="logError" class="error-msg">{{ logError }}</p>
        <p v-if="logLoading" class="status-msg">Loading log stats...</p>

        <div v-if="logStats && !logLoading" class="log-grid">
          <div>
            <h3>Summary</h3>
            <ul class="stat-list">
              <li><strong>Map:</strong> {{ logStats.map }}</li>
              <li><strong>Entries:</strong> {{ logStats.summary.entries }}</li>
              <li><strong>Total Kills:</strong> {{ logStats.summary.total_kills }}</li>
              <li><strong>Average DPM:</strong> {{ logStats.summary.avg_dpm }}</li>
            </ul>
          </div>
          <div>
            <h3>Players</h3>
            <table v-if="logStats.stats.length">
              <thead>
                <tr>
                  <th>Player</th>
                  <th>SteamID</th>
                  <th>Class</th>
                  <th>K/D</th>
                  <th>DPM</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="entry in logStats.stats" :key="`${entry.steamid}-${entry.class}`">
                  <td>
                    <RouterLink
                      class="inline-link"
                      :to="playerPath(entry.steamid)"
                    >
                      {{ entry.player_name }}
                    </RouterLink>
                  </td>
                  <td>
                    <RouterLink
                      class="inline-link mono"
                      :to="playerPath(entry.steamid)"
                    >
                      {{ entry.steamid }}
                    </RouterLink>
                  </td>
                  <td>{{ entry.class }}</td>
                  <td>{{ entry.kills }}/{{ entry.deaths }}</td>
                  <td>{{ entry.dpm }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-head">
          <h2>All Matches</h2>
          <p class="status-msg">Showing {{ matches.length }} of {{ matchesTotal }} total matches</p>
        </div>

        <p v-if="matchesError" class="error-msg">{{ matchesError }}</p>
        <p v-if="matchesLoading" class="status-msg">Loading matches...</p>

        <table v-if="!matchesLoading && matches.length">
          <thead>
            <tr>
              <th>Log ID</th>
              <th>Map</th>
              <th>Tournament</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="match in matches" :key="match.id">
              <td>
                <RouterLink class="inline-link mono" :to="logPath(match.log_id)">
                  {{ match.log_id }}
                </RouterLink>
              </td>
              <td>{{ match.map }}</td>
              <td>{{ formatTournamentName(match) }}</td>
            </tr>
          </tbody>
        </table>

        <p v-if="!matchesLoading && !matchesError && !matches.length" class="status-msg">
          No matches found.
        </p>

        <div class="leaderboard-pagination">
          <button
            :disabled="matchesLoading || matchesPage <= 1"
            @click="goToPage(matchesPage - 1)"
          >
            Previous
          </button>
          <span>Page {{ matchesPage }} / {{ totalPages() }}</span>
          <button
            :disabled="matchesLoading || matchesPage >= totalPages()"
            @click="goToPage(matchesPage + 1)"
          >
            Next
          </button>
        </div>
      </section>
    </main>
  </div>
</template>
