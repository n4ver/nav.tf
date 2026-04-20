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
  await router.replace({ name: 'match-stats', params: { logId: String(logId.value) } })
  await loadLogStats()
}

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
            <h3>Top Performers</h3>
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
                <tr v-for="entry in logStats.stats.slice(0, 8)" :key="`${entry.steamid}-${entry.class}`">
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
    </main>
  </div>
</template>
