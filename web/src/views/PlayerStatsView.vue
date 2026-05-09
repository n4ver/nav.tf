<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
// import { convertSteamID3toSteamID64, createSteamURL } from '../helper'
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

function convertSteamID3toSteamID64(steamid) {
    const steamNumber = 76561197960265728n; // Magic number to add to account number for conversion
    const regex = /^\[U:\d:(\d+)\]$/;
    const match = steamid.match(regex);

    if (!match) return null;

    const accountId = BigInt(match[1]);
    const steam64 = accountId + steamNumber;
    return steam64.toString();
}

function createSteamURL(steamid64) {
    return "https://steamcommunity.com/profiles/" + steamid64;
}

const steamId = ref(decodeSteamId(route.params.steamId))
const selectedClassId = ref(0)

const tf2Classes = [
  { id: 0, name: 'Scout' },
  { id: 1, name: 'Soldier' },
  { id: 2, name: 'Pyro' },
  { id: 3, name: 'Demoman' },
  { id: 4, name: 'Heavy' },
  { id: 5, name: 'Engineer' },
  { id: 6, name: 'Medic' },
  { id: 7, name: 'Sniper' },
  { id: 8, name: 'Spy' },
]

const playerSummary = ref(null)
const playerLoading = ref(false)
const playerError = ref('')

const playerClassAggregate = ref(null)
const classLoading = ref(false)
const classError = ref('')

async function loadPlayerSummary() {
  playerLoading.value = true
  playerError.value = ''

  try {
    const encodedSteamId = encodeURIComponent(steamId.value)
    playerSummary.value = await fetchJson(`/players/${encodedSteamId}/summary`)
  } catch (error) {
    playerSummary.value = null
    playerError.value = error instanceof Error ? error.message : 'Failed to load player summary'
  } finally {
    playerLoading.value = false
  }
}

async function loadPlayerClassAggregate() {
  if (!steamId.value) {
    return
  }

  classLoading.value = true
  classError.value = ''

  try {
    const encodedSteamId = encodeURIComponent(steamId.value)
    playerClassAggregate.value = await fetchJson(`/player/${encodedSteamId}/${selectedClassId.value}`)
  } catch (error) {
    playerClassAggregate.value = null
    classError.value = error instanceof Error ? error.message : 'Failed to load class aggregate'
  } finally {
    classLoading.value = false
  }
}

function formatRating(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A'
  }
  return value.toFixed(3)
}

async function submitAndLoad() {
  const encodedSteamId = encodeURIComponent(steamId.value)
  await router.replace(`/player/${encodedSteamId}`)
  await loadPlayerSummary()
  await loadPlayerClassAggregate()
}

watch(
  () => route.params.steamId,
  async (nextSteamId) => {
    if (!nextSteamId) {
      return
    }
    steamId.value = decodeSteamId(nextSteamId)
    await loadPlayerSummary()
    await loadPlayerClassAggregate()
  },
)

watch(
  selectedClassId,
  async () => {
    if (!route.params.steamId) {
      return
    }
    await loadPlayerClassAggregate()
  },
)

onMounted(async () => {
  if (route.params.steamId) {
    await loadPlayerSummary()
    await loadPlayerClassAggregate()
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
          <p class="rating-chip">
            Average Rating: <strong>{{ formatRating(playerSummary.aggregate_stats.avg_rating) }}</strong>
          </p>
            <h2>
              <strong><a :href="createSteamURL(convertSteamID3toSteamID64(steamId))">{{ playerSummary.player_name || steamId }}</a></strong>
            </h2>

            <div class="split">
              <article>
                <h3>Aggregate Stats</h3>
                <ul class="stat-list">
                  <li><strong>Matches:</strong> {{ playerSummary.aggregate_stats.matches_played }}</li>
                  <li><strong>Avg Rating:</strong> {{ formatRating(playerSummary.aggregate_stats.avg_rating) }}</li>
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
                <h3>Class Aggregate</h3>
                <label>
                  Class
                  <select v-model.number="selectedClassId">
                    <option v-for="tf2Class in tf2Classes" :key="tf2Class.id" :value="tf2Class.id">
                      {{ tf2Class.name }}
                    </option>
                  </select>
                </label>
                <p v-if="classError" class="error-msg">{{ classError }}</p>
                <p v-if="classLoading" class="status-msg">Loading class aggregate...</p>

                <ul v-if="playerClassAggregate && !classLoading" class="stat-list">
                  <li><strong>Class:</strong> {{ playerClassAggregate.class_name }}</li>
                  <li><strong>Matches:</strong> {{ playerClassAggregate.aggregate_stats.matches_played }}</li>
                  <li><strong>Avg Rating:</strong> {{ formatRating(playerClassAggregate.aggregate_stats.avg_rating) }}</li>
                  <li><strong>Total Kills:</strong> {{ playerClassAggregate.aggregate_stats.total_kills }}</li>
                  <li><strong>Total Deaths:</strong> {{ playerClassAggregate.aggregate_stats.total_deaths }}</li>
                  <li><strong>Avg DPM:</strong> {{ playerClassAggregate.aggregate_stats.avg_dpm }}</li>
                  <li><strong>Avg KDR:</strong> {{ playerClassAggregate.aggregate_stats.avg_kdr }}</li>
                  <li><strong>Playtime (mins):</strong> {{ playerClassAggregate.aggregate_stats.total_playtime_mins }}</li>
                  <li><strong>Damage Dealt:</strong> {{ playerClassAggregate.aggregate_stats.total_damage_dealt }}</li>
                  <li><strong>Damage Received:</strong> {{ playerClassAggregate.aggregate_stats.total_damage_received }}</li>
                  <li><strong>Heals Received:</strong> {{ playerClassAggregate.aggregate_stats.total_heals_received }}</li>
                </ul>
              </article>
            </div>

            <h3 style="margin-top: 1rem">Matches Participated</h3>
            <table v-if="playerSummary.matches.length">
              <thead>
                <tr>
                  <th>Log ID</th>
                  <th>Map</th>
                  <th>Team</th>
                  <th>K/D</th>
                  <th>DPM</th>
                  <th>Rating</th>
                  <th>Playtime</th>
                  <th>Heals</th>
                  <th>Total Ubers</th>
                  <th>Total Drops</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="match in playerSummary.matches" :key="match.match_id">
                  <td>
                    <RouterLink
                      class="inline-link mono"
                      :to="{ name: 'match-stats', params: { logId: String(match.log_id) } }"
                    >
                      {{ match.log_id }}
                    </RouterLink>
                  </td>
                  <td>{{ match.map }}</td>
                  <td>{{ match.team }}</td>
                  <td>{{ match.kills }}/{{ match.deaths }}</td>
                  <td>{{ match.dpm }}</td>
                  <td>{{ formatRating(match.rating) }}</td>
                  <td>{{ match.playtime_mins }}m</td>
                  <td>{{ match.heals_received }}</td>
                  <td>{{ match.total_ubers }}</td>
                  <td>{{ match.total_drops }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="status-msg">No matches found for this player.</p>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.rating-chip {
  margin: 0.35rem 0;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.36rem 0.62rem;
  border-radius: 999px;
  background: rgba(12, 79, 115, 0.12);
  border: 1px solid rgba(12, 79, 115, 0.3);
  color: #0b415e;
}
</style>
