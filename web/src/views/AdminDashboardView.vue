<script setup>
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import LogUploadForm from '../components/LogUploadForm.vue'
import LogsTfIngestor from '../components/LogsTfIngestor.vue'
import { createTournament, fetchTournaments, searchQuery, updatePlayerDisplayName, updateTournament } from '../api'
import { useAuthStore } from '../stores/auth'
import { useCan } from '../composables/useCan'

const auth = useAuthStore()
const { displayName, steamId } = storeToRefs(auth)
const { allowed: canAdmin } = useCan('ADMIN')

const playerQuery = ref('')
const playerResults = ref([])
const playerSearchLoading = ref(false)
const playerSearchError = ref('')
const aliasDrafts = ref({})
const aliasStatus = ref('')

const tournamentName = ref('')
const tournamentSlug = ref('')
const tournamentStart = ref('')
const tournamentStatus = ref('')
const tournamentError = ref('')
const editingTournamentId = ref('')
const editingName = ref('')
const editingSlug = ref('')

const tournaments = ref([])
const tournamentsLoading = ref(false)

async function loadTournaments() {
  tournamentsLoading.value = true
  try {
    const rows = await fetchTournaments()
    tournaments.value = Array.isArray(rows) ? rows : []
  } catch (error) {
    tournamentError.value = error instanceof Error ? error.message : 'Failed to load tournaments'
  } finally {
    tournamentsLoading.value = false
  }
}

async function searchPlayers() {
  const q = playerQuery.value.trim()
  if (!q) {
    playerSearchError.value = 'Enter a SteamID or display name fragment.'
    return
  }
  playerSearchLoading.value = true
  playerSearchError.value = ''
  aliasStatus.value = ''
  try {
    const results = await searchQuery(q, { limit: 20 })
    playerResults.value = results.filter((result) => result.kind === 'player')
    if (!playerResults.value.length) {
      playerSearchError.value = 'No players found.'
    }
  } catch (error) {
    playerSearchError.value = error instanceof Error ? error.message : 'Search failed'
    playerResults.value = []
  } finally {
    playerSearchLoading.value = false
  }
}

async function saveAlias(result) {
  const steam = result.steam_id
  const display = String(aliasDrafts.value[steam] || '').trim()
  if (!display) {
    aliasStatus.value = 'Display name cannot be empty.'
    return
  }
  try {
    await updatePlayerDisplayName({ steam_id: steam, display_name: display })
    aliasStatus.value = `Updated alias for ${steam} → ${display}`
    result.display_name = display
    result.label = display
  } catch (error) {
    aliasStatus.value = error instanceof Error ? error.message : 'Failed to update alias'
  }
}

async function submitCreateTournament() {
  tournamentStatus.value = ''
  tournamentError.value = ''
  try {
    const payload = {
      name: tournamentName.value.trim(),
      slug: tournamentSlug.value.trim(),
    }
    if (tournamentStart.value) {
      payload.start_date = new Date(tournamentStart.value).toISOString()
    }
    const result = await createTournament(payload)
    tournamentStatus.value = `Created tournament ${result.name} (${result.tournament_id})`
    tournamentName.value = ''
    tournamentSlug.value = ''
    tournamentStart.value = ''
    await loadTournaments()
  } catch (error) {
    tournamentError.value = error instanceof Error ? error.message : 'Create failed'
  }
}

function beginEdit(tournament) {
  editingTournamentId.value = String(tournament.tournament_id)
  editingName.value = tournament.name
  editingSlug.value = tournament.slug
}

async function submitUpdateTournament() {
  if (!editingTournamentId.value) return
  tournamentStatus.value = ''
  tournamentError.value = ''
  try {
    const result = await updateTournament(editingTournamentId.value, {
      name: editingName.value.trim(),
      slug: editingSlug.value.trim(),
    })
    tournamentStatus.value = `Updated tournament ${result.name}`
    editingTournamentId.value = ''
    await loadTournaments()
  } catch (error) {
    tournamentError.value = error instanceof Error ? error.message : 'Update failed'
  }
}

onMounted(async () => {
  if (canAdmin.value) {
    await loadTournaments()
  }
})
</script>

<template>
  <div class="page-wrap">
    <header class="hero">
      <p class="eyebrow">Administration</p>
      <h1>Admin Dashboard</h1>
      <p>
        Signed in as {{ displayName }}
        <span class="mono text-sm">({{ steamId }})</span>
      </p>
    </header>

    <p v-if="!canAdmin" class="error-msg page-error">Admin role required.</p>

    <main v-else class="content-grid space-y-4">
      <section class="panel">
        <div class="panel-head">
          <h2>Upload log</h2>
        </div>
        <LogUploadForm />
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Ingest from logs.tf</h2>
        </div>
        <LogsTfIngestor />
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Player display names</h2>
        </div>
        <form class="space-y-3" @submit.prevent="searchPlayers">
          <label class="flex flex-col gap-1 text-sm">
            Search players
            <input v-model="playerQuery" type="text" placeholder="SteamID or name" />
          </label>
          <button type="submit" :disabled="playerSearchLoading">
            {{ playerSearchLoading ? 'Searching…' : 'Search' }}
          </button>
        </form>
        <p v-if="playerSearchError" class="error-msg">{{ playerSearchError }}</p>
        <p v-if="aliasStatus" class="status-msg">{{ aliasStatus }}</p>
        <table v-if="playerResults.length" class="mt-4">
          <thead>
            <tr>
              <th>Steam ID</th>
              <th>Current name</th>
              <th>New alias</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="result in playerResults" :key="result.steam_id">
              <td class="mono text-sm">{{ result.steam_id }}</td>
              <td>{{ result.display_name || result.label }}</td>
              <td>
                <input
                  v-model="aliasDrafts[result.steam_id]"
                  type="text"
                  :placeholder="result.display_name || 'Custom alias'"
                />
              </td>
              <td>
                <button type="button" @click="saveAlias(result)">Save</button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Tournaments</h2>
        </div>
        <form class="space-y-3" @submit.prevent="submitCreateTournament">
          <div class="grid gap-3 sm:grid-cols-3">
            <label class="flex flex-col gap-1 text-sm">
              Name
              <input v-model="tournamentName" type="text" required placeholder="Invite Bracket" />
            </label>
            <label class="flex flex-col gap-1 text-sm">
              Slug
              <input v-model="tournamentSlug" type="text" required placeholder="invite-bracket" />
            </label>
            <label class="flex flex-col gap-1 text-sm">
              Start date
              <input v-model="tournamentStart" type="datetime-local" />
            </label>
          </div>
          <button type="submit">Create tournament</button>
        </form>
        <p v-if="tournamentError" class="error-msg">{{ tournamentError }}</p>
        <p v-if="tournamentStatus" class="status-msg">{{ tournamentStatus }}</p>

        <p v-if="tournamentsLoading" class="status-msg">Loading tournaments…</p>
        <table v-else-if="tournaments.length" class="mt-4">
          <thead>
            <tr>
              <th>Name</th>
              <th>Slug</th>
              <th>Matches</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="tournament in tournaments" :key="tournament.tournament_id">
              <td>
                <template v-if="editingTournamentId === String(tournament.tournament_id)">
                  <input v-model="editingName" type="text" />
                </template>
                <template v-else>{{ tournament.name }}</template>
              </td>
              <td>
                <template v-if="editingTournamentId === String(tournament.tournament_id)">
                  <input v-model="editingSlug" type="text" />
                </template>
                <template v-else>{{ tournament.slug }}</template>
              </td>
              <td>{{ tournament.match_count }}</td>
              <td>
                <button
                  v-if="editingTournamentId !== String(tournament.tournament_id)"
                  type="button"
                  @click="beginEdit(tournament)"
                >
                  Edit
                </button>
                <button
                  v-else
                  type="button"
                  @click="submitUpdateTournament"
                >
                  Save
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>
  </div>
</template>
