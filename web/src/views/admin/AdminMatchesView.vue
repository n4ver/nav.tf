<script setup>
import { onMounted, ref } from 'vue'
import Panel from '../../components/ui/Panel.vue'
import StateMessage from '../../components/ui/StateMessage.vue'
import SkeletonBlock from '../../components/ui/SkeletonBlock.vue'
import { assignMatchTournament, fetchMatches, fetchTournaments } from '../../api'
import { pollUntil } from '../../utils/poll'


const matches = ref([])
const tournaments = ref([])
const loading = ref(false)
const error = ref('')
const status = ref('')
const drafts = ref({})
const savingId = ref('')

function tournamentLabel(id) {
  const match = tournaments.value.find((row) => String(row.tournament_id) === String(id))
  return match ? match.name : id ? String(id).slice(0, 8) : 'Unassigned'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [matchRows, tournamentRows] = await Promise.all([
      fetchMatches({ skip: 0, limit: 50 }),
      fetchTournaments(),
    ])
    matches.value = Array.isArray(matchRows) ? matchRows : []
    tournaments.value = Array.isArray(tournamentRows) ? tournamentRows : []
    const next = {}
    for (const match of matches.value) {
      next[match.match_id] = String(match.tournament_id || '')
    }
    drafts.value = next
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load matches'
  } finally {
    loading.value = false
  }
}

async function saveAssignment(match) {
  const tournamentId = drafts.value[match.match_id]
  if (!tournamentId) {
    status.value = 'Select a tournament before saving.'
    return
  }
  status.value = ''
  error.value = ''
  savingId.value = String(match.match_id)
  try {
    await assignMatchTournament(match.match_id, { tournament_id: tournamentId })
    await pollUntil(async () => {
      await load()
      const row = matches.value.find((item) => String(item.match_id) === String(match.match_id))
      return String(row?.tournament_id || '') === String(tournamentId)
    })
    status.value = `Assigned match to ${tournamentLabel(tournamentId)}`
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Assignment failed'
  } finally {
    savingId.value = ''
  }
}

onMounted(load)
</script>

<template>
  <Panel title="Matches">
    <template #actions>
      <button type="button" class="btn-ghost" :disabled="loading" @click="load">Refresh</button>
    </template>
    <p class="text-sm text-ink-muted">Reassign a projected match to a tournament. Ratings stay; leaderboards refresh.</p>
    <StateMessage v-if="error" tone="error" class="mt-2">{{ error }}</StateMessage>
    <StateMessage v-if="status" tone="info" class="mt-2">{{ status }}</StateMessage>
    <div v-if="loading" class="mt-4" aria-busy="true" aria-label="Loading matches">
      <SkeletonBlock :rows="4" />
    </div>
    <div v-else-if="matches.length" class="mt-4 overflow-x-auto rounded-sm border border-line">
      <table class="w-full min-w-[720px] border-collapse text-sm">
        <thead class="bg-surface-900">
          <tr>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Match</th>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Map</th>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Tournament</th>
            <th class="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="match in matches"
            :key="match.match_id"
            class="border-t border-line even:bg-surface-900/40"
          >
            <td class="px-2.5 py-1.5 font-mono text-xs text-ink">
              <RouterLink class="focus-ring rounded text-blu hover:text-accent" :to="`/match/${match.match_id}`">
                {{ String(match.match_id).slice(0, 8) }}…
              </RouterLink>
            </td>
            <td class="px-2.5 py-1.5 text-ink">{{ match.map_name }}</td>
            <td class="px-3 py-2">
              <select
                v-model="drafts[match.match_id]"
                class="field"
                :aria-label="`Tournament for match ${String(match.match_id).slice(0, 8)}`"
              >
                <option value="">Select tournament</option>
                <option
                  v-for="tournament in tournaments"
                  :key="tournament.tournament_id"
                  :value="String(tournament.tournament_id)"
                >
                  {{ tournament.name }}
                </option>
              </select>
            </td>
            <td class="px-3 py-2">
              <button
                type="button"
                class="btn-primary"
                :disabled="savingId === String(match.match_id)"
                @click="saveAssignment(match)"
              >
                {{ savingId === String(match.match_id) ? 'Saving…' : 'Save' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <StateMessage v-else class="mt-3">No matches projected yet.</StateMessage>
  </Panel>
</template>
