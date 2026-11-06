<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchMatchaSourceStatus, ingestMatchaMatch, pollMatcha } from '../../api'
import { useMatchQueryStore } from '../../stores/matchQuery'
import { usePlayerQueryStore } from '../../stores/playerQuery'
import { useRatingQueryStore } from '../../stores/ratingQuery'
import { errorMessage } from '../../utils/format'

const emit = defineEmits(['ingested'])

const matchQuery = useMatchQueryStore()
const playerQuery = usePlayerQueryStore()
const ratingQuery = useRatingQueryStore()

/** null = checking */
const sourceStatus = ref(null)
const matchaMatchId = ref('')
const resetIdempotency = ref(false)
const busy = ref('') // '' | 'match' | 'poll'
const error = ref('')
const result = ref(null)

const statusLabel = computed(() => {
  if (sourceStatus.value === null) return 'Checking api-consumer…'
  if (!sourceStatus.value.configured) return 'api-consumer not configured'
  return sourceStatus.value.reachable ? 'api-consumer online' : 'api-consumer unreachable'
})
const statusTone = computed(() => {
  if (sourceStatus.value === null) return 'bg-ink-muted'
  return sourceStatus.value.configured && sourceStatus.value.reachable ? 'bg-ok' : 'bg-danger'
})

async function loadStatus() {
  try {
    sourceStatus.value = await fetchMatchaSourceStatus()
  } catch {
    sourceStatus.value = { configured: false, reachable: false }
  }
}

onMounted(loadStatus)

function refreshCaches() {
  playerQuery.clear()
  ratingQuery.invalidate()
  return matchQuery.loadMatches({ page: 1 })
}

async function onIngestMatch() {
  if (busy.value) return
  busy.value = 'match'
  error.value = ''
  result.value = null
  const id = Number(matchaMatchId.value)
  try {
    const body = await ingestMatchaMatch({ match_id: id })
    const published = Array.isArray(body?.published) ? body.published : []
    result.value = {
      kind: 'match',
      title: body?.noLogs
        ? `matcha.tf match #${id} has no logs.tf logs yet`
        : `matcha.tf match #${id}: ${Number(body?.accepted) || 0} log(s) published, ${Number(body?.skipped) || 0} already ingested`,
      matchIds: published.map((row) => row.matchId).filter(Boolean),
    }
    await refreshCaches()
    emit('ingested', result.value.matchIds)
  } catch (err) {
    error.value = errorMessage(err, 'matcha.tf ingest failed')
  } finally {
    busy.value = ''
  }
}

async function onPoll() {
  if (busy.value) return
  busy.value = 'poll'
  error.value = ''
  result.value = null
  try {
    const body = await pollMatcha({ reset: resetIdempotency.value })
    result.value = {
      kind: 'poll',
      title:
        `Poll finished: ${Number(body?.matchIds) || 0} match(es) listed, `
        + `${Number(body?.accepted) || 0} log(s) published, ${Number(body?.skipped) || 0} skipped, `
        + `${Number(body?.noLogs) || 0} without logs, ${Number(body?.failed) || 0} failed`,
      failedMatchIds: Array.isArray(body?.failedMatchIds) ? body.failedMatchIds : [],
      matchIds: [],
    }
    await refreshCaches()
    emit('ingested', [])
  } catch (err) {
    error.value = errorMessage(err, 'matcha.tf poll failed')
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="text-sm text-ink-muted">
        Runs the api-consumer's
        <code class="font-mono text-xs text-ink">MatchaAdapter</code>: reads the series from
        <a
          class="focus-ring rounded font-medium text-blu transition hover:text-accent"
          href="https://matcha.tf"
          target="_blank"
          rel="noreferrer"
        >matcha.tf</a>,
        pulls each map's stats from logs.tf and publishes them to the read model. Matches land in
        the api-consumer's configured tournament; reassign them under Matches.
      </p>
      <span class="inline-flex items-center gap-1.5 text-xs text-ink-muted" role="status" data-test="matcha-status">
        <span class="h-2 w-2 rounded-full" :class="statusTone" aria-hidden="true" />
        {{ statusLabel }}
      </span>
    </div>

    <form class="flex flex-wrap items-end gap-3" data-test="matcha-match-form" @submit.prevent="onIngestMatch">
      <label class="label-caps min-w-[12rem] flex-1">
        matcha.tf match ID
        <input
          v-model="matchaMatchId"
          type="number"
          min="1"
          step="1"
          inputmode="numeric"
          placeholder="e.g. 201"
          class="field"
          :disabled="!!busy"
          required
        />
      </label>
      <button type="submit" class="btn-primary px-5" :disabled="!!busy || !matchaMatchId">
        {{ busy === 'match' ? 'Ingesting…' : 'Ingest match' }}
      </button>
    </form>

    <div class="flex flex-wrap items-center gap-3 border-t border-line pt-4">
      <button type="button" class="btn-ghost" :disabled="!!busy" data-test="matcha-poll" @click="onPoll">
        {{ busy === 'poll' ? 'Polling league…' : 'Poll configured league now' }}
      </button>
      <label class="inline-flex items-center gap-2 text-sm text-ink-muted">
        <input v-model="resetIdempotency" type="checkbox" :disabled="!!busy" />
        Re-publish matches already seen
      </label>
    </div>

    <p v-if="error" class="text-sm font-medium text-danger" role="alert">{{ error }}</p>

    <div v-else-if="result" class="space-y-1 text-sm" role="status" data-test="matcha-result">
      <p class="text-ok">{{ result.title }}</p>
      <ul v-if="result.matchIds.length" class="flex flex-wrap gap-2">
        <li v-for="id in result.matchIds" :key="id">
          <RouterLink class="data-link font-mono text-xs" :to="{ name: 'match-stats', params: { matchId: id } }">
            {{ String(id).slice(0, 8) }}…
          </RouterLink>
        </li>
      </ul>
      <p v-if="result.failedMatchIds?.length" class="text-xs text-danger">
        Failed: {{ result.failedMatchIds.join(', ') }}
      </p>
    </div>
  </div>
</template>
