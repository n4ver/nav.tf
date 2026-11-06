<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { convertToSteamID64 } from '../../utils/steam'
import { searchQuery } from '../../api'
import { useAuthStore } from '../../stores/auth'
import { useCan } from '../../composables/useCan'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { allowed: canAdmin } = useCan('ADMIN')

/* ---- Primary navigation ------------------------------------------------ */

const baseLinks = [
  { to: '/', name: 'tournament', label: 'Home' },
  { to: '/match', name: 'match-stats', label: 'Matches' },
  { to: '/event', name: 'event', label: 'Events' },
  { to: '/player', name: 'player-stats', label: 'Players' },
]
const adminLink = { to: '/admin', name: 'admin', label: 'Admin' }
const links = computed(() => (canAdmin.value ? [...baseLinks, adminLink] : baseLinks))

function isActive(link) {
  if (link === adminLink) return String(route.path || '').startsWith('/admin')
  return route.name === link.name
}

const menuOpen = ref(false)

watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false
  },
)

function onKeydown(event) {
  if (event.key === 'Escape') {
    menuOpen.value = false
    lookupResults.value = []
  }
}

function onResize() {
  if (window.innerWidth >= 1024) menuOpen.value = false
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', onResize)
})

/* ---- Search ------------------------------------------------------------ */

const lookupValue = ref('')
const lookupError = ref('')
const lookupLoading = ref(false)
const lookupResults = ref([])

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const STEAM_RE = /^(STEAM_[0-5]:[01]:\d+|\[U:\d:\d+\]|\d{17})$/i

function clientFallback(query) {
  if (UUID_RE.test(query) || /^\d+$/.test(query)) {
    if (STEAM_RE.test(query)) {
      return { name: 'player-stats', params: { steamId: convertToSteamID64(query) || query } }
    }
    return { name: 'match-stats', params: { matchId: query } }
  }
  if (STEAM_RE.test(query)) {
    return { name: 'player-stats', params: { steamId: convertToSteamID64(query) || query } }
  }
  return null
}

function routeFromResult(result) {
  if ((result.kind === 'match' || result.kind === 'log') && result.match_id) {
    return { name: 'match-stats', params: { matchId: String(result.match_id) } }
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
  lookupError.value = ''
}

async function navigateToResult(result) {
  const target = routeFromResult(result)
  if (!target) {
    lookupError.value = 'Cannot open that search result.'
    return
  }
  await router.push(target)
  lookupValue.value = ''
  lookupResults.value = []
}

async function submitLookup() {
  const query = lookupValue.value.trim()
  if (!query) {
    lookupError.value = 'Enter a player name, SteamID, logs.tf ID, or match UUID.'
    return
  }

  lookupLoading.value = true
  clearLookupResults()

  try {
    const results = await searchQuery(query, { limit: 8 })
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
</script>

<template>
  <header class="sticky top-0 z-30 border-b border-line bg-surface-900">
    <div class="mx-auto flex h-12 w-full max-w-[1400px] items-center gap-3 px-3 lg:px-4">
      <RouterLink
        to="/"
        class="focus-ring flex shrink-0 items-center gap-2 rounded-sm"
        aria-label="nav.tf home"
        data-test="brand"
      >
        <span class="text-base font-black tracking-tight text-ink">nav.tf</span>
      </RouterLink>

      <nav class="hidden h-full items-stretch lg:flex" aria-label="Primary">
        <RouterLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="focus-ring flex items-center border-b-2 px-3 text-sm font-semibold transition-colors"
          :class="
            isActive(link)
              ? 'border-accent text-ink'
              : 'border-transparent text-ink-muted hover:text-ink'
          "
          :aria-current="isActive(link) ? 'page' : undefined"
          :data-test="`nav-${link.name}`"
        >
          {{ link.label }}
        </RouterLink>
      </nav>

      <div class="relative ml-auto min-w-0 flex-1 sm:max-w-sm">
        <form class="flex" role="search" @submit.prevent="submitLookup">
          <input
            v-model="lookupValue"
            type="search"
            placeholder="Player, SteamID, logs.tf ID…"
            aria-label="Search players, SteamIDs, logs.tf IDs or match UUIDs"
            aria-controls="lookup-results"
            class="h-8 min-w-0 flex-1 rounded-l-sm border border-line bg-surface-950 px-2.5 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
            @input="clearLookupResults"
          />
          <button
            type="submit"
            :disabled="lookupLoading"
            class="focus-ring h-8 shrink-0 rounded-r-sm bg-surface-700 px-3 text-sm font-semibold text-ink hover:bg-surface-600 disabled:opacity-50"
          >
            {{ lookupLoading ? '…' : 'Search' }}
          </button>
        </form>
        <ul
          v-if="lookupResults.length"
          id="lookup-results"
          class="absolute left-0 right-0 top-[calc(100%+4px)] z-40 list-none overflow-hidden rounded-sm border border-line bg-surface-800 shadow-xl"
          aria-label="Search results"
        >
          <li v-for="result in lookupResults" :key="`${result.kind}-${result.id}`">
            <button
              type="button"
              class="focus-ring flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-surface-700"
              @click="navigateToResult(result)"
            >
              <span class="w-12 shrink-0 text-[0.65rem] font-bold uppercase text-ink-muted">
                {{ kindLabel(result.kind) }}
              </span>
              <span class="truncate text-ink">{{ result.label }}</span>
            </button>
          </li>
        </ul>
      </div>

      <div class="hidden shrink-0 items-center gap-2 sm:flex">
        <template v-if="auth.isAuthenticated">
          <span class="max-w-[9rem] truncate text-sm font-semibold text-ink" :title="auth.steamId">
            {{ auth.displayName }}
          </span>
          <button type="button" class="btn-ghost text-xs" @click="auth.logout()">Log out</button>
        </template>
        <button v-else type="button" class="btn-primary" @click="auth.beginSteamLogin()">
          Sign in through Steam
        </button>
      </div>

      <button
        type="button"
        class="focus-ring inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-line text-ink lg:hidden"
        :aria-label="menuOpen ? 'Close navigation' : 'Open navigation'"
        aria-controls="mobile-nav"
        :aria-expanded="menuOpen"
        data-test="menu-toggle"
        @click="menuOpen = !menuOpen"
      >
        <span aria-hidden="true">{{ menuOpen ? '✕' : '☰' }}</span>
      </button>
    </div>

    <p
      v-if="lookupError"
      role="alert"
      class="border-t border-danger/30 bg-danger/10 px-4 py-1 text-center text-sm text-danger"
    >
      {{ lookupError }}
    </p>

    <nav
      v-show="menuOpen"
      id="mobile-nav"
      class="border-t border-line bg-surface-900 px-3 pb-3 pt-1 lg:hidden"
      aria-label="Primary mobile"
      data-test="mobile-nav"
    >
      <RouterLink
        v-for="link in links"
        :key="link.to"
        :to="link.to"
        class="focus-ring block rounded-sm px-2 py-2 text-sm font-semibold"
        :class="isActive(link) ? 'bg-surface-700 text-accent' : 'text-ink-muted hover:text-ink'"
        :aria-current="isActive(link) ? 'page' : undefined"
      >
        {{ link.label }}
      </RouterLink>
      <div class="mt-2 border-t border-line pt-2 sm:hidden">
        <template v-if="auth.isAuthenticated">
          <p class="truncate px-2 pb-2 text-sm text-ink">{{ auth.displayName }}</p>
          <button type="button" class="btn-ghost w-full" @click="auth.logout()">Log out</button>
        </template>
        <button v-else type="button" class="btn-primary w-full" @click="auth.beginSteamLogin()">
          Sign in through Steam
        </button>
      </div>
    </nav>
  </header>
</template>
