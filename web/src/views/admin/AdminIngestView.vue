<script setup>
import { onMounted, ref } from 'vue'
import Panel from '../../components/ui/Panel.vue'
import StateMessage from '../../components/ui/StateMessage.vue'
import LogUploadForm from '../../components/admin/LogUploadForm.vue'
import LogsTfIngestor from '../../components/admin/LogsTfIngestor.vue'
import { fetchTournaments } from '../../api'

const tournaments = ref([])
const selectedTournamentId = ref('')
const loadError = ref('')

async function loadTournaments() {
  loadError.value = ''
  try {
    const rows = await fetchTournaments()
    tournaments.value = Array.isArray(rows) ? rows : []
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : 'Failed to load tournaments'
  }
}

onMounted(loadTournaments)
</script>

<template>
  <div class="space-y-4">
    <Panel>
      <label class="label-caps">
        Target tournament
        <select
          v-model="selectedTournamentId"
          class="field"
        >
          <option value="">Default tournament</option>
          <option
            v-for="tournament in tournaments"
            :key="tournament.tournament_id"
            :value="String(tournament.tournament_id)"
          >
            {{ tournament.name }} ({{ tournament.slug }})
          </option>
        </select>
      </label>
      <StateMessage v-if="loadError" tone="error" class="mt-2">{{ loadError }}</StateMessage>
    </Panel>

    <Panel title="Upload log">
      <LogUploadForm :tournament-id="selectedTournamentId" />
    </Panel>

    <Panel title="Ingest from logs.tf">
      <LogsTfIngestor :tournament-id="selectedTournamentId" />
    </Panel>
  </div>
</template>
