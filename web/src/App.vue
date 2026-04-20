<script setup>
import { computed, onMounted, ref, watch } from 'vue'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

const health = ref(null)
const healthError = ref('')

const tournamentId = ref(1)
const selectedClass = ref('Scout')
const leaderboard = ref([])
const matches = ref([])
const tournamentLoading = ref(false)
const tournamentError = ref('')
const rowsPerClassPage = 5
const classPageByName = ref({})

const logId = ref(123456)
const logStats = ref(null)
const logLoading = ref(false)
const logError = ref('')

const steamId = ref('')
const playerSummary = ref(null)
const playerLoading = ref(false)
const playerError = ref('')

const tf2ClassOrder = [
  'Scout',
  'Soldier',
  'Pyro',
  'Demoman',
  'Heavy',
  'Engineer',
  'Medic',
  'Sniper',
  'Spy',
]

const classSortRank = new Map(
  tf2ClassOrder.map((name, index) => [name.toLowerCase(), index]),
)

function clampPage(page, totalPages) {
  return Math.min(Math.max(page, 1), totalPages)
}

function setClassPage(className, nextPage, totalPages) {
  classPageByName.value = {
    ...classPageByName.value,
    [className]: clampPage(nextPage, totalPages),
  }
}

const leaderboardByClass = computed(() => {
  const grouped = new Map()

  for (const row of leaderboard.value) {
    const className = row.class || 'Unknown'
    if (!grouped.has(className)) {
      grouped.set(className, [])
    }
    grouped.get(className).push(row)
  }

  const sections = Array.from(grouped.entries()).map(([className, rows]) => {
    const sortedRows = rows.slice().sort((a, b) => b.avg_dpm - a.avg_dpm)
    const totalPages = Math.max(1, Math.ceil(sortedRows.length / rowsPerClassPage))
    const rawPage = classPageByName.value[className] || 1
    const currentPage = clampPage(rawPage, totalPages)
    const startIndex = (currentPage - 1) * rowsPerClassPage

    return {
      className,
      rows: sortedRows,
      pagedRows: sortedRows.slice(startIndex, startIndex + rowsPerClassPage),
      currentPage,
      totalPages,
      startRow: startIndex + 1,
      endRow: Math.min(startIndex + rowsPerClassPage, sortedRows.length),
    }
  })

  sections.sort((a, b) => {
    const aRank = classSortRank.get(String(a.className).toLowerCase())
    const bRank = classSortRank.get(String(b.className).toLowerCase())

    if (aRank !== undefined && bRank !== undefined) {
      return aRank - bRank
    }
    if (aRank !== undefined) {
      return -1
    }
    if (bRank !== undefined) {
      return 1
    }
    return String(a.className).localeCompare(String(b.className))
  })

  return sections
})

async function fetchJson(path) {
  const response = await fetch(`${apiBaseUrl}${path}`)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`${response.status} ${response.statusText}${text ? `: ${text}` : ''}`)
  }
  return response.json()
}

async function loadHealth() {
  healthError.value = ''
  try {
    health.value = await fetchJson('/health/')
  } catch (error) {
    health.value = null
    healthError.value = error instanceof Error ? error.message : 'Failed to check API health'
  }
}

async function loadTournamentData() {
  tournamentLoading.value = true
  tournamentError.value = ''

  try {
    const [leaderboardData, matchesData] = await Promise.all([
      fetchJson(`/tournaments/${tournamentId.value}/leaderboard?class_name=${encodeURIComponent(selectedClass.value)}&limit=10`),
      fetchJson(`/tournaments/${tournamentId.value}/matches?limit=10&offset=0`),
    ])
    leaderboard.value = leaderboardData
    matches.value = matchesData
  } catch (error) {
    leaderboard.value = []
    matches.value = []
    tournamentError.value = error instanceof Error ? error.message : 'Failed to load tournament data'
  } finally {
    tournamentLoading.value = false
  }
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

async function loadPlayerSummary() {
  playerLoading.value = true
  playerError.value = ''

  try {
    playerSummary.value = await fetchJson(`/players/${steamId.value}/summary`)
  } catch (error) {
    playerSummary.value = null
    playerError.value = error instanceof Error ? error.message : 'Failed to load player summary'
  } finally {
    playerLoading.value = false
  }
}

onMounted(async () => {
  await loadHealth()
  await loadTournamentData()
})

watch(selectedClass, async () => {
  await loadTournamentData()
})
</script>

<template>
  <div class="page-wrap">
    <header class="hero">
      <p class="eyebrow">TF2 analytics dashboard</p>
      <h1>FastAPI + Vite Viewer</h1>
      <p>
        Frontend talks to <code>{{ apiBaseUrl }}</code> and renders tournament, log, and player data.
      </p>
      <div class="health-chip" :class="{ bad: healthError }">
        <strong>API health:</strong>
        <span v-if="health">{{ health.status }}</span>
        <span v-else-if="healthError">Unavailable</span>
        <span v-else>Checking...</span>
      </div>
      <p v-if="healthError" class="error-msg">{{ healthError }}</p>
    </header>

    <main class="content-grid">
      <section class="panel">
        <div class="panel-head">
          <h2>Tournament</h2>
          <form @submit.prevent="loadTournamentData">
            <label>
              Tournament ID
              <input v-model.number="tournamentId" type="number" min="1" required />
            </label>
            <label>
              Class
              <select v-model="selectedClass">
                <option value="Scout">Scout</option>
                <option value="Soldier">Soldier</option>
                <option value="Pyro">Pyro</option>
                <option value="Demoman">Demoman</option>
                <option value="Heavy">Heavy</option>
                <option value="Engineer">Engineer</option>
                <option value="Medic">Medic</option>
                <option value="Sniper">Sniper</option>
                <option value="Spy">Spy</option>
              </select>
            </label>
            <button type="submit" :disabled="tournamentLoading">Load</button>
          </form>
        </div>

        <p v-if="tournamentError" class="error-msg">{{ tournamentError }}</p>
        <p v-if="tournamentLoading" class="status-msg">Loading tournament data...</p>

        <div class="split" v-if="!tournamentLoading && !tournamentError">
          <article>
            <h3>Leaderboard</h3>
            <div v-if="leaderboardByClass.length" class="leaderboard-class-grid">
              <section v-for="group in leaderboardByClass" :key="group.className" class="leaderboard-class-group">
                <h4>{{ group.className }}</h4>
                <table v-if="selectedClass.toLowerCase() === 'medic'">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Avg HPM</th>
                      <th>Total Drops</th>
                      <th>Avg Deaths</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="player in group.pagedRows" :key="`${player.steamid}-${group.className}`">
                      <td>{{ player.name }}</td>
                      <td>{{ player.avg_hpm }}</td>
                      <td>{{ player.total_drops }}</td>
                      <td>{{ player.avg_deaths }}</td>
                    </tr>
                  </tbody>
                </table>
                <table v-else>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Avg DPM</th>
                      <th>Avg Kills</th>
                      <th>Avg Deaths</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="player in group.pagedRows" :key="`${player.steamid}-${group.className}`">
                      <td>{{ player.name }}</td>
                      <td>{{ player.avg_dpm }}</td>
                      <td>{{ player.avg_kills }}</td>
                      <td>{{ player.avg_deaths }}</td>
                    </tr>
                  </tbody>
                </table>
                <div class="leaderboard-pagination" v-if="group.rows.length > rowsPerClassPage">
                  <button
                    type="button"
                    :disabled="group.currentPage === 1"
                    @click="setClassPage(group.className, group.currentPage - 1, group.totalPages)"
                  >
                    Prev
                  </button>
                  <span>
                    {{ group.startRow }}-{{ group.endRow }} of {{ group.rows.length }}
                    (Page {{ group.currentPage }}/{{ group.totalPages }})
                  </span>
                  <button
                    type="button"
                    :disabled="group.currentPage === group.totalPages"
                    @click="setClassPage(group.className, group.currentPage + 1, group.totalPages)"
                  >
                    Next
                  </button>
                </div>
              </section>
            </div>
            <p v-else class="status-msg">No leaderboard rows returned.</p>
          </article>

          <article>
            <h3>Recent Matches</h3>
            <table v-if="matches.length">
              <thead>
                <tr>
                  <th>Log ID</th>
                  <th>Map</th>
                  <th>Tournament</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="match in matches" :key="match.id">
                  <td>{{ match.log_id }}</td>
                  <td>{{ match.map }}</td>
                  <td>{{ match.tournament_id }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="status-msg">No matches for this tournament yet.</p>
          </article>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Log Stats</h2>
          <form @submit.prevent="loadLogStats">
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
            <h3>Top Performers</h3>
            <table v-if="logStats.stats.length">
              <thead>
                <tr>
                  <th>Player</th>
                  <th>Class</th>
                  <th>K/D</th>
                  <th>DPM</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="entry in logStats.stats.slice(0, 8)" :key="`${entry.steamid}-${entry.class}`">
                  <td>{{ entry.player_name }}</td>
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
          <h2>Player Summary</h2>
          <form @submit.prevent="loadPlayerSummary">
            <label>
              SteamID
              <input v-model.trim="steamId" placeholder="7656119..." required />
            </label>
            <button type="submit" :disabled="playerLoading">Lookup</button>
          </form>
        </div>

        <p v-if="playerError" class="error-msg">{{ playerError }}</p>
        <p v-if="playerLoading" class="status-msg">Loading player summary...</p>

        <div v-if="playerSummary && !playerLoading">
          <p class="status-msg">
            Classification: <strong>{{ playerSummary.ai_classification }}</strong>
          </p>
          <table v-if="playerSummary.class_breakdown.length">
            <thead>
              <tr>
                <th>Class</th>
                <th>Avg DPM</th>
                <th>Kills</th>
                <th>Matches</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in playerSummary.class_breakdown" :key="row.class_name">
                <td>{{ row.class_name }}</td>
                <td>{{ row.avg_dpm }}</td>
                <td>{{ row.sum_kills }}</td>
                <td>{{ row.matches_played }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
</template>
