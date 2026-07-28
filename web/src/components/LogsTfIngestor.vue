<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useMatchCommandStore } from '../stores/matchCommand'
import { useMatchQueryStore } from '../stores/matchQuery'
import { usePlayerQueryStore } from '../stores/playerQuery'
import { useRatingQueryStore } from '../stores/ratingQuery'

const emit = defineEmits(['ingested'])

const router = useRouter()
const commandStore = useMatchCommandStore()
const queryStore = useMatchQueryStore()
const playerQuery = usePlayerQueryStore()
const ratingQuery = useRatingQueryStore()
const { ingestingLogsTf, parsing, isBusy, error, statusMessage, lastMatchId } = storeToRefs(commandStore)

const logstfId = ref('')
const toast = ref({ visible: false, kind: 'success', message: '' })
let toastTimer = null

function showToast(kind, message) {
  if (toastTimer != null) {
    clearTimeout(toastTimer)
  }
  toast.value = { visible: true, kind, message }
  toastTimer = setTimeout(() => {
    toast.value.visible = false
  }, 4500)
}

async function onSubmit() {
  if (isBusy.value) {
    return
  }

  const result = await commandStore.ingestFromLogsTf(Number(logstfId.value))
  if (!result?.matchId) {
    showToast('error', error.value || 'Ingest failed')
    return
  }

  const successLabel =
    result.status === 'skipped'
      ? `Already ingested — match ${result.matchId}`
      : `Ingested logs.tf #${logstfId.value}`

  showToast('success', successLabel)

  queryStore.invalidateMatch(result.matchId)
  playerQuery.clear()
  ratingQuery.invalidate()
  await queryStore.loadMatches({ page: 1 })
  if (result.detail) {
    await queryStore.loadMatchDetail(result.matchId, { force: true })
  }
  emit('ingested', result.matchId)

  await router.push({
    name: 'match-stats',
    params: { matchId: String(result.matchId) },
  })
}
</script>

<template>
  <form class="relative space-y-4" @submit.prevent="onSubmit">
    <p class="text-sm text-slate-600">
      Fetch match stats directly from
      <a
        class="font-medium text-sky-700 underline-offset-2 hover:underline"
        href="https://logs.tf"
        target="_blank"
        rel="noreferrer"
      >logs.tf</a>
      by ID — no raw log upload required.
    </p>

    <label class="flex flex-col gap-1 text-sm text-slate-700">
      logs.tf ID
      <input
        v-model="logstfId"
        type="number"
        min="1"
        step="1"
        inputmode="numeric"
        placeholder="e.g. 3209041"
        class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-sky-600 focus:ring-2 focus:ring-sky-200"
        :disabled="isBusy"
        required
      />
    </label>

    <div class="flex flex-wrap items-center gap-3">
      <button
        type="submit"
        class="rounded-full bg-sky-700 px-5 py-2 text-sm font-semibold text-white transition hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="isBusy || !logstfId"
      >
        <span v-if="ingestingLogsTf">Fetching…</span>
        <span v-else-if="parsing">Projecting…</span>
        <span v-else>Ingest from logs.tf</span>
      </button>

      <p
        v-if="parsing || ingestingLogsTf"
        class="inline-flex items-center gap-2 rounded-full bg-amber-100 px-3 py-1.5 text-sm font-medium text-amber-900"
        role="status"
        aria-live="polite"
      >
        <span class="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
        {{ ingestingLogsTf ? 'Contacting logs.tf…' : 'Waiting for MatchParsed…' }}
      </p>

      <p v-else-if="statusMessage && !error" class="text-sm text-emerald-700">
        {{ statusMessage }}
        <span v-if="lastMatchId" class="ml-1 font-mono text-xs text-slate-500">{{ lastMatchId }}</span>
      </p>
    </div>

    <p v-if="error" class="text-sm font-medium text-red-700" role="alert">{{ error }}</p>

    <div
      v-if="toast.visible"
      class="pointer-events-none fixed bottom-6 right-6 z-50 max-w-sm rounded-lg px-4 py-3 text-sm font-medium shadow-lg"
      :class="toast.kind === 'success'
        ? 'bg-emerald-800 text-emerald-50'
        : 'bg-red-800 text-red-50'"
      role="status"
      aria-live="polite"
    >
      {{ toast.message }}
    </div>
  </form>
</template>
