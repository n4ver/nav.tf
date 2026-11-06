<script setup>
import { ref } from 'vue'
import { useLogIngestion } from '../../composables/useLogIngestion'
import { useMatchQueryStore } from '../../stores/matchQuery'
import { usePlayerQueryStore } from '../../stores/playerQuery'
import { useRatingQueryStore } from '../../stores/ratingQuery'

const emit = defineEmits(['uploaded'])

const props = defineProps({
  tournamentId: {
    type: String,
    default: '',
  },
})

const queryStore = useMatchQueryStore()
const playerQuery = usePlayerQueryStore()
const ratingQuery = useRatingQueryStore()
const {
  uploading,
  parsing,
  isBusy,
  error,
  statusMessage,
  lastMatchId,
  submitAndNavigate,
} = useLogIngestion()

const logData = ref('')
const timestamp = ref(new Date().toISOString().slice(0, 19))

async function onSubmit() {
  if (isBusy.value) {
    return
  }

  const result = await submitAndNavigate({
    mode: 'upload',
    payload: {
      log_data: logData.value,
      timestamp: timestamp.value ? new Date(timestamp.value).toISOString() : undefined,
      ...(props.tournamentId ? { tournament_id: props.tournamentId } : {}),
    },
    onReady: async ({ matchId, detail }) => {
      queryStore.invalidateMatch(matchId)
      playerQuery.clear()
      ratingQuery.invalidate()
      await queryStore.loadMatches({ page: 1 })
      if (detail) {
        await queryStore.loadMatchDetail(matchId, { force: true })
      }
      emit('uploaded', matchId)
    },
  })

  if (!result?.matchId) {
    return
  }
}
</script>

<template>
  <form class="space-y-4" @submit.prevent="onSubmit">
    <div class="grid gap-3 sm:grid-cols-2">
      <label class="label-caps">
        Timestamp
        <input
          v-model="timestamp"
          type="datetime-local"
          class="field"
          :disabled="isBusy"
          required
        />
      </label>
    </div>

    <label class="label-caps">
      Raw log data
      <textarea
        v-model="logData"
        rows="6"
        class="field font-mono"
        placeholder="map_name=cp_process_final blu_score=2 red_score=1 player steam_id=STEAM_1:1:12345 team=blu class=scout kills=10 deaths=5 ..."
        :disabled="isBusy"
        required
      />
    </label>

    <div class="flex flex-wrap items-center gap-3">
      <button
        type="submit"
        class="btn-primary px-5"
        :disabled="isBusy || !logData.trim()"
      >
        <span v-if="uploading">Uploading…</span>
        <span v-else-if="parsing">Parsing…</span>
        <span v-else>Upload log</span>
      </button>

      <p
        v-if="parsing"
        class="inline-flex items-center gap-2 rounded-full border border-warn/30 bg-warn/10 px-3 py-1.5 text-sm font-medium text-warn"
        role="status"
        aria-live="polite"
      >
        <span class="h-2 w-2 animate-pulse rounded-full bg-warn" aria-hidden="true" />
        Parsing in progress…
      </p>

      <p v-else-if="statusMessage && !error" class="text-sm text-ok">
        {{ statusMessage }}
        <span v-if="lastMatchId" class="ml-1 font-mono text-xs text-ink-muted">{{ lastMatchId }}</span>
      </p>
    </div>

    <p v-if="error" class="text-sm font-medium text-danger" role="alert">{{ error }}</p>
  </form>
</template>
