<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { usePlayerQueryStore } from '../stores/playerQuery'
import PlayerStatsTable from '../components/PlayerStatsTable.vue'
import { formatRating, ratingTone } from '../utils/rating'
import { createSteamURL, convertToSteamID64 } from '../utils/steam'

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

function formatNumber(value, digits = 2) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A'
  }
  return value.toFixed(digits)
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

function matchPath(matchId) {
  return `/match/${encodeURIComponent(String(matchId))}`
}

async function submitAndLoad() {
  const raw = steamId.value.trim()
  if (!raw) {
    return
  }
  const query = convertToSteamID64(raw) || raw

  await router.replace({
    name: 'player-stats',
    params: { steamId: query },
  })
  await playerQuery.loadPlayerStats(query, { force: true })
}

watch(
  () => route.params.steamId,
  async (nextSteamId) => {
    if (!nextSteamId) {
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
  }
})
</script>

<template>
  <div class="page-wrap">
    <header class="hero">
      <p class="eyebrow">TF2 analytics dashboard</p>
      <h1>Player Statistics</h1>
      <p>Lifetime aggregates, class splits, and ratings from the Query service.</p>
    </header>

    <main class="content-grid">
      <section class="panel">
        <div class="panel-head">
          <h2>Player lifetime stats</h2>
          <form @submit.prevent="submitAndLoad">
            <label>
              SteamID
              <input v-model.trim="steamId" placeholder="76561198… or STEAM_1:1:12345" required />
            </label>
            <button type="submit" :disabled="loading">Lookup</button>
          </form>
        </div>

        <p v-if="error" class="error-msg">{{ error }}</p>

        <div v-if="loading" class="space-y-3" aria-busy="true" aria-label="Loading player stats">
          <div class="h-8 w-48 animate-pulse rounded bg-gray-200" />
          <div class="grid gap-2 sm:grid-cols-2">
            <div v-for="n in 6" :key="n" class="h-10 animate-pulse rounded bg-gray-200" />
          </div>
        </div>

        <div v-else-if="stats">
          <div class="mb-3">
            <a
              v-if="createSteamURL(stats.steam_id)"
              class="inline-link"
              :href="createSteamURL(stats.steam_id)"
              target="_blank"
              rel="noopener noreferrer"
            >
              Open Steam profile
            </a>
          </div>
          <PlayerStatsTable :stats="stats" :format-number="formatNumber" />

          <div class="mt-4" v-if="stats.recent_matches?.length">
            <h3>Recent matches</h3>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Map</th>
                  <th>Team</th>
                  <th>Classes</th>
                  <th>K/D/A</th>
                  <th>DPM</th>
                  <th>Rating</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in stats.recent_matches" :key="row.match_id">
                  <td>
                    <RouterLink class="inline-link" :to="matchPath(row.match_id)">
                      {{ formatDate(row.date_played) }}
                    </RouterLink>
                  </td>
                  <td>{{ row.map_name }}</td>
                  <td>{{ row.team }}</td>
                  <td>{{ classesLabel(row.classes_played) }}</td>
                  <td>{{ row.kills }}/{{ row.deaths }}/{{ row.assists }}</td>
                  <td>{{ formatNumber(row.damage_per_minute, 1) }}</td>
                  <td>
                    <span class="rating-chip" :class="`tone-${ratingTone(row.rating)}`">
                      {{ formatRating(row.rating) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p v-else-if="stats.matches_played > 0" class="status-msg mt-3">
            No recent match history available yet.
          </p>

          <p v-if="stats.matches_played === 0" class="status-msg mt-3">
            No projected stats yet for this SteamID. Upload a log that includes this player.
          </p>
        </div>
      </section>
    </main>
  </div>
</template>
