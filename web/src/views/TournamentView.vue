<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { fetchJson, getApiBaseUrl } from '../api'

const apiBaseUrl = getApiBaseUrl()

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

function playerPath(steamId) {
  if (!steamId) {
    return null
  }
  return `/player/${encodeURIComponent(steamId)}`
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

async function loadHealth() {
  healthError.value = ''
  try {
    health.value = await fetchJson('/health')
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
      <h1>Tournament Dashboard</h1>
      <p>
        Frontend talks to <code>{{ apiBaseUrl }}</code> and renders tournament analytics.
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
                      <td>
                        <RouterLink
                          v-if="player.steamid"
                          class="inline-link"
                          :to="playerPath(player.steamid)"
                        >
                          {{ player.name }}
                        </RouterLink>
                        <span v-else>{{ player.name }}</span>
                      </td>
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
                      <td>
                        <RouterLink
                          v-if="player.steamid"
                          class="inline-link"
                          :to="playerPath(player.steamid)"
                        >
                          {{ player.name }}
                        </RouterLink>
                        <span v-else>{{ player.name }}</span>
                      </td>
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
                  <td>
                    <RouterLink
                      class="inline-link mono"
                      :to="{ name: 'match-stats', params: { logId: String(match.log_id) } }"
                    >
                      {{ match.log_id }}
                    </RouterLink>
                  </td>
                  <td>{{ match.map }}</td>
                  <td>{{ match.tournament_id }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="status-msg">No matches for this tournament yet.</p>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>
