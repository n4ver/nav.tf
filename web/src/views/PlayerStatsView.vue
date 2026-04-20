<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchJson } from '../api'

const route = useRoute()
const router = useRouter()

function decodeSteamId(value) {
  try {
    return decodeURIComponent(String(value || ''))
  } catch {
    return String(value || '')
  }
}

const steamId = ref(decodeSteamId(route.params.steamId))
const playerSummary = ref(null)
const playerLoading = ref(false)
const playerError = ref('')

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

async function submitAndLoad() {
  const encodedSteamId = encodeURIComponent(steamId.value)
  await router.replace(`/player/${encodedSteamId}`)
  await loadPlayerSummary()
}

watch(
  () => route.params.steamId,
  async (nextSteamId) => {
    if (!nextSteamId) {
      return
    }
    steamId.value = decodeSteamId(nextSteamId)
    await loadPlayerSummary()
  },
)

onMounted(async () => {
  if (route.params.steamId) {
    await loadPlayerSummary()
  }
})
</script>

<template>
  <div class="page-wrap">
    <header class="hero">
      <p class="eyebrow">TF2 analytics dashboard</p>
      <h1>Player Statistics</h1>
      <p>Look up a specific player and inspect class-level performance.</p>
    </header>

    <main class="content-grid">
      <section class="panel">
        <div class="panel-head">
          <h2>Player Summary</h2>
          <form @submit.prevent="submitAndLoad">
            <label>
              SteamID
              <input v-model.trim="steamId" placeholder="[U:1:963..." required />
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
            <p>
              <strong>{{ playerSummary.player_name || steamId }}</strong>
            </p>

            <div class="split">
              <article>
                <h3>Aggregate Stats</h3>
                <ul class="stat-list">
                  <li><strong>Matches:</strong> {{ playerSummary.aggregate_stats.matches_played }}</li>
                  <li><strong>Total Kills:</strong> {{ playerSummary.aggregate_stats.total_kills }}</li>
                  <li><strong>Total Deaths:</strong> {{ playerSummary.aggregate_stats.total_deaths }}</li>
                  <li><strong>Avg DPM:</strong> {{ playerSummary.aggregate_stats.avg_dpm }}</li>
                  <li><strong>Avg KDR:</strong> {{ playerSummary.aggregate_stats.avg_kdr }}</li>
                  <li><strong>Playtime (mins):</strong> {{ playerSummary.aggregate_stats.total_playtime_mins }}</li>
                  <li><strong>Damage Dealt:</strong> {{ playerSummary.aggregate_stats.total_damage_dealt }}</li>
                  <li><strong>Damage Received:</strong> {{ playerSummary.aggregate_stats.total_damage_received }}</li>
                  <li><strong>Heals Received:</strong> {{ playerSummary.aggregate_stats.total_heals_received }}</li>
                </ul>
              </article>

              <article>
                <h3>Class Breakdown</h3>
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
              </article>
            </div>

            <h3 style="margin-top: 1rem">Matches Participated</h3>
            <table v-if="playerSummary.matches.length">
              <thead>
                <tr>
                  <th>Log ID</th>
                  <th>Map</th>
                  <th>Class</th>
                  <th>K/D</th>
                  <th>DPM</th>
                  <th>Playtime</th>
                  <th>Heals</th>
                  <th>Ubers</th>
                  <th>Drops</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="match in playerSummary.matches" :key="`${match.match_id}-${match.class_name}`">
                  <td>
                    <RouterLink
                      class="inline-link mono"
                      :to="{ name: 'match-stats', params: { logId: String(match.log_id) } }"
                    >
                      {{ match.log_id }}
                    </RouterLink>
                  </td>
                  <td>{{ match.map }}</td>
                  <td>{{ match.class_name }}</td>
                  <td>{{ match.kills }}/{{ match.deaths }}</td>
                  <td>{{ match.dpm }}</td>
                  <td>{{ match.playtime_mins }}m</td>
                  <td>{{ match.heals_received }}</td>
                  <td>{{ match.ubers }}</td>
                  <td>{{ match.drops }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="status-msg">No matches found for this player.</p>
        </div>
      </section>
    </main>
  </div>
</template>
