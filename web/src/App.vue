<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { convertToSteamID64 } from './utils/steam'
import { searchQuery } from './api'
import { useAuthStore } from './stores/auth'
import { useCan } from './composables/useCan'

const router = useRouter()
const auth = useAuthStore()
const { allowed: canAdmin } = useCan('ADMIN')

const lookupValue = ref('')
const lookupError = ref('')
const lookupLoading = ref(false)
const lookupResults = ref([])

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const STEAM_RE = /^(STEAM_[0-5]:[01]:\d+|\[U:\d:\d+\]|\d{17})$/i

function normalizeSteamRouteId(query) {
  return convertToSteamID64(query) || query
}

function clientFallback(query) {
  if (UUID_RE.test(query)) {
    return { name: 'match-stats', params: { matchId: query } }
  }
  if (/^\d+$/.test(query)) {
    return { name: 'match-stats', params: { matchId: query } }
  }
  if (STEAM_RE.test(query)) {
    return { name: 'player-stats', params: { steamId: normalizeSteamRouteId(query) } }
  }
  return null
}

function routeFromResult(result) {
  if (result.kind === 'match' || result.kind === 'log') {
    if (result.match_id) {
      return { name: 'match-stats', params: { matchId: String(result.match_id) } }
    }
  }
  if (result.kind === 'player' && result.steam_id) {
    return { name: 'player-stats', params: { steamId: String(result.steam_id) } }
  }
  return null
}

function kindLabel(kind) {
  if (kind === 'log') return 'Log'
  if (kind === 'match') return 'Match'
  if (kind === 'player') return 'Player'
  return kind || 'Result'
}

function clearLookupResults() {
  lookupResults.value = []
}

async function navigateToResult(result) {
  const target = routeFromResult(result)
  if (!target) {
    lookupError.value = 'Cannot open that search result.'
    return
  }
  await router.push(target)
  lookupValue.value = ''
  clearLookupResults()
}

async function submitLookup() {
  const query = lookupValue.value.trim()
  if (!query) {
    lookupError.value = 'Enter a match UUID, logs.tf ID, or SteamID.'
    return
  }

  lookupLoading.value = true
  lookupError.value = ''
  clearLookupResults()

  try {
    const results = await searchQuery(query, { limit: 5 })
    const routable = results.filter((result) => routeFromResult(result))

    if (routable.length > 1) {
      lookupResults.value = routable
      return
    }

    if (routable.length === 1) {
      await navigateToResult(routable[0])
      return
    }

    const fallback = clientFallback(query)
    if (!fallback) {
      throw new Error('No match or player found for that query.')
    }
    await router.push(fallback)
    lookupValue.value = ''
  } catch (error) {
    lookupError.value = error instanceof Error ? error.message : 'Lookup failed'
  } finally {
    lookupLoading.value = false
  }
}

onMounted(() => {
  auth.bootstrap()
})
</script>

<template>
  <div>
    <nav class="top-nav">
      <RouterLink to="/" class="nav-link">Tournament</RouterLink>
      <RouterLink to="/match" class="nav-link">Match Statistics</RouterLink>
      <RouterLink to="/player" class="nav-link">Player Statistics</RouterLink>
      <RouterLink v-if="canAdmin" to="/admin/dashboard" class="nav-link">Admin</RouterLink>
      <div class="quick-lookup-wrap">
        <form class="quick-lookup" @submit.prevent="submitLookup">
          <input
            v-model="lookupValue"
            type="text"
            placeholder="Lookup log ID, match UUID, or SteamID"
            aria-label="Lookup log ID, match UUID, or SteamID"
            :aria-expanded="lookupResults.length > 0"
            aria-controls="lookup-results"
            @input="clearLookupResults"
          />
          <button type="submit" :disabled="lookupLoading">
            {{ lookupLoading ? 'Searching…' : 'Go' }}
          </button>
        </form>
        <ul
          v-if="lookupResults.length"
          id="lookup-results"
          class="lookup-results"
          role="listbox"
          aria-label="Search results"
        >
          <li v-for="result in lookupResults" :key="`${result.kind}-${result.id}`">
            <button type="button" class="lookup-result-btn" @click="navigateToResult(result)">
              <span class="lookup-result-kind">{{ kindLabel(result.kind) }}</span>
              <span class="lookup-result-label">{{ result.label }}</span>
            </button>
          </li>
        </ul>
      </div>
      <div class="auth-controls">
        <template v-if="auth.isAuthenticated">
          <span class="auth-user" :title="auth.steamId">{{ auth.displayName }}</span>
          <span class="auth-role">{{ auth.role }}</span>
          <button type="button" class="nav-link auth-btn" @click="auth.logout()">Log out</button>
        </template>
        <button v-else type="button" class="nav-link auth-btn" @click="auth.beginSteamLogin()">
          Log in with Steam
        </button>
      </div>
    </nav>
    <p v-if="lookupError" class="error-msg page-error">{{ lookupError }}</p>
    <RouterView />
  </div>
</template>
