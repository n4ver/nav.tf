<script setup>
import { onUnmounted, ref } from 'vue'
import { useLogIngestion } from '../../composables/useLogIngestion'
import { useMatchQueryStore } from '../../stores/matchQuery'
import { usePlayerQueryStore } from '../../stores/playerQuery'
import { useRatingQueryStore } from '../../stores/ratingQuery'

const emit = defineEmits(['ingested'])

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
  ingestingLogsTf,
  parsing,
  isBusy,
  error,
  statusMessage,
  lastMatchId,
  submitAndNavigate,
} = useLogIngestion()

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

onUnmounted(() => {
  if (toastTimer != null) clearTimeout(toastTimer)
})

async function onSubmit() {
  if (isBusy.value) {
    return
  }

  const result = await submitAndNavigate({
    mode: 'ingest-logstf',
    payload: {
      logstf_id: Number(logstfId.value),
      ...(props.tournamentId ? { tournament_id: props.tournamentId } : {}),
    },
    onReady: async ({ matchId, detail, status }) => {
      const successLabel =
        status === 'skipped'
          ? `Already ingested — match ${matchId}`
          : `Ingested logs.tf #${logstfId.value}`
      showToast('success', successLabel)

      queryStore.invalidateMatch(matchId)
      playerQuery.clear()
      ratingQuery.invalidate()
      await queryStore.loadMatches({ page: 1 })
      if (detail) {
        await queryStore.loadMatchDetail(matchId, { force: true })
      }
      emit('ingested', matchId)
    },
  })

  if (!result?.matchId) {
    showToast('error', error.value || 'Ingest failed')
  }
}
</script>

<template>
  <form class="relative space-y-4" @submit.prevent="onSubmit">
    <p class="text-sm text-ink-muted">
      Fetch match stats directly from
      <a
        class="focus-ring rounded font-medium text-blu transition hover:text-accent"
        href="https://logs.tf"
        target="_blank"
        rel="noreferrer"
      >logs.tf</a>
      by ID.
    </p>

    <label class="label-caps">
      logs.tf ID
      <input
        v-model="logstfId"
        type="number"
        min="1"
        step="1"
        inputmode="numeric"
        placeholder="e.g. 3209041"
        class="field"
        :disabled="isBusy"
        required
      />
    </label>

    <div class="flex flex-wrap items-center gap-3">
      <button
        type="submit"
        class="btn-primary px-5"
        :disabled="isBusy || !logstfId"
      >
        <span v-if="ingestingLogsTf">Fetching…</span>
        <span v-else-if="parsing">Projecting…</span>
        <span v-else>Ingest from logs.tf</span>
      </button>

      <p
        v-if="parsing || ingestingLogsTf"
        class="inline-flex items-center gap-2 rounded-full border border-warn/30 bg-warn/10 px-3 py-1.5 text-sm font-medium text-warn"
        role="status"
        aria-live="polite"
      >
        <span class="h-2 w-2 animate-pulse rounded-full bg-warn" aria-hidden="true" />
        {{ ingestingLogsTf ? 'Contacting logs.tf…' : 'Waiting for MatchParsed…' }}
      </p>

      <p v-else-if="statusMessage && !error" class="text-sm text-ok">
        {{ statusMessage }}
        <span v-if="lastMatchId" class="ml-1 font-mono text-xs text-ink-muted">{{ lastMatchId }}</span>
      </p>
    </div>

    <p v-if="error" class="text-sm font-medium text-danger" role="alert">{{ error }}</p>

    <div
      v-if="toast.visible"
      class="pointer-events-none fixed bottom-6 right-6 z-50 max-w-sm rounded-sm px-4 py-3 text-sm font-medium shadow-lg"
      :class="toast.kind === 'success'
        ? 'bg-ok text-white'
        : 'bg-danger text-white'"
      role="status"
      aria-live="polite"
    >
      {{ toast.message }}
    </div>
  </form>
</template>
