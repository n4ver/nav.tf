<script setup>
import { ref } from 'vue'
import Panel from '../../components/ui/Panel.vue'
import StateMessage from '../../components/ui/StateMessage.vue'
import { searchQuery, updatePlayerDisplayName } from '../../api'


const playerQuery = ref('')
const playerResults = ref([])
const playerSearchLoading = ref(false)
const playerSearchError = ref('')
const aliasDrafts = ref({})
const aliasStatus = ref('')

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
</script>

<template>
  <Panel title="Player display names">
    <form class="space-y-3" @submit.prevent="searchPlayers">
      <label class="label-caps">
        Search players
        <input v-model="playerQuery" type="text" placeholder="SteamID or name" class="field" />
      </label>
      <button type="submit" :disabled="playerSearchLoading" class="btn-primary">
        {{ playerSearchLoading ? 'Searching…' : 'Search' }}
      </button>
    </form>
    <StateMessage v-if="playerSearchError" tone="error" class="mt-2">{{ playerSearchError }}</StateMessage>
    <StateMessage v-if="aliasStatus" tone="info" class="mt-2">{{ aliasStatus }}</StateMessage>
    <div v-if="playerResults.length" class="mt-4 overflow-x-auto rounded-sm border border-line">
      <table class="w-full min-w-[640px] border-collapse text-sm">
        <thead class="bg-surface-900">
          <tr>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Steam ID</th>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Current name</th>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">New alias</th>
            <th class="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="result in playerResults"
            :key="result.steam_id"
            class="border-t border-line even:bg-surface-900/40"
          >
            <td class="px-2.5 py-1.5 font-mono text-xs text-ink">{{ result.steam_id }}</td>
            <td class="px-2.5 py-1.5 text-ink">{{ result.display_name || result.label }}</td>
            <td class="px-3 py-2">
              <input
                v-model="aliasDrafts[result.steam_id]"
                type="text"
                :aria-label="`New alias for ${result.steam_id}`"
                :placeholder="result.display_name || 'Custom alias'"
                class="field"
              />
            </td>
            <td class="px-3 py-2">
              <button type="button" class="btn-ghost" @click="saveAlias(result)">Save</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </Panel>
</template>
