<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useMatchCommandStore } from '../stores/matchCommand'
import { useMatchQueryStore } from '../stores/matchQuery'
import { usePlayerQueryStore } from '../stores/playerQuery'
import { useRatingQueryStore } from '../stores/ratingQuery'

const emit = defineEmits(['uploaded'])

const router = useRouter()
const commandStore = useMatchCommandStore()
const queryStore = useMatchQueryStore()
const playerQuery = usePlayerQueryStore()
const ratingQuery = useRatingQueryStore()
const { uploading, parsing, isBusy, error, statusMessage, lastMatchId } = storeToRefs(commandStore)

const serverId = ref('')
const logData = ref('')
const timestamp = ref(new Date().toISOString().slice(0, 19))

async function onSubmit() {
  if (isBusy.value) {
    return
  }

  const result = await commandStore.submitLogUpload({
    log_data: logData.value,
    timestamp: timestamp.value ? new Date(timestamp.value).toISOString() : undefined,
  })

  if (!result?.matchId) {
    return
  }

  queryStore.invalidateMatch(result.matchId)
  playerQuery.clear()
  ratingQuery.invalidate()
  await queryStore.loadMatches({ page: 1 })
  if (result.detail) {
    // Seed detail cache with the rated MatchParsed projection.
    await queryStore.loadMatchDetail(result.matchId, { force: true })
  }
  emit('uploaded', result.matchId)

  await router.push({
    name: 'match-stats',
    params: { matchId: String(result.matchId) },
  })
}
</script>

<template>
  <form class="space-y-4" @submit.prevent="onSubmit">
    <div class="grid gap-3 sm:grid-cols-2">

      <label class="flex flex-col gap-1 text-sm text-slate-700">
        Timestamp
        <input
          v-model="timestamp"
          type="datetime-local"
          class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-sky-600 focus:ring-2 focus:ring-sky-200"
          :disabled="isBusy"
          required
        />
      </label>
    </div>

    <label class="flex flex-col gap-1 text-sm text-slate-700">
      Raw log data
      <textarea
        v-model="logData"
        rows="6"
        class="rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm outline-none focus:border-sky-600 focus:ring-2 focus:ring-sky-200"
        placeholder="map_name=cp_process_final blu_score=2 red_score=1 player steam_id=STEAM_1:1:12345 team=blu class=scout kills=10 deaths=5 ..."
        :disabled="isBusy"
        required
      />
    </label>

    <div class="flex flex-wrap items-center gap-3">
      <button
        type="submit"
        class="rounded-full bg-orange-500 px-5 py-2 text-sm font-semibold text-white transition hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="isBusy || !logData.trim()"
      >
        <span v-if="uploading">Uploading...</span>
        <span v-else-if="parsing">Parsing...</span>
        <span v-else>Upload log</span>
      </button>

      <p
        v-if="parsing"
        class="inline-flex items-center gap-2 rounded-full bg-amber-100 px-3 py-1.5 text-sm font-medium text-amber-900"
        role="status"
        aria-live="polite"
      >
        <span class="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
        Parsing in progress...
      </p>

      <p v-else-if="statusMessage && !error" class="text-sm text-emerald-700">
        {{ statusMessage }}
        <span v-if="lastMatchId" class="ml-1 font-mono text-xs text-slate-500">{{ lastMatchId }}</span>
      </p>
    </div>

    <p v-if="error" class="text-sm font-medium text-red-700" role="alert">{{ error }}</p>
  </form>
</template>
