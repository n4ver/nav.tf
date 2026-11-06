<script setup>
import { computed } from 'vue'
import { formatDate, formatDuration } from '../../utils/format'

const props = defineProps({
  summary: {
    type: Object,
    required: true,
  },
  /** Resolved tournament name; falls back to nothing when unknown. */
  tournamentName: {
    type: String,
    default: '',
  },
})

function toScore(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

const winner = computed(() => String(props.summary.winning_team || '').toLowerCase())
const bluScore = computed(() => toScore(props.summary.blu_score))
const redScore = computed(() => toScore(props.summary.red_score))
const bluWon = computed(() => winner.value === 'blu')
const redWon = computed(() => winner.value === 'red')
const logsTfUrl = computed(() =>
  props.summary.source_log_id != null ? `https://logs.tf/${props.summary.source_log_id}` : null,
)
</script>

<template>
  <article class="overflow-hidden rounded-sm border border-line bg-surface-800" data-test="scorebox">
    <div class="grid grid-cols-[1fr_auto_1fr] items-center">
      <div
        class="flex items-center justify-end gap-3 border-r-4 px-4 py-4 sm:gap-5 sm:px-6"
        :class="bluWon ? 'border-blu bg-blu-deep/50' : 'border-transparent bg-surface-800'"
      >
        <span class="text-lg font-black uppercase tracking-wider text-blu sm:text-2xl">BLU</span>
      </div>

      <div class="flex items-center gap-2 px-4 py-4 sm:gap-4 sm:px-6" aria-label="Final score">
        <span
          class="text-4xl font-black tabular-nums sm:text-5xl"
          :class="bluWon ? 'text-ok' : redWon ? 'text-danger' : 'text-ink'"
          data-test="blu-score"
        >{{ bluScore }}</span>
        <span class="text-2xl text-ink-muted" aria-hidden="true">:</span>
        <span
          class="text-4xl font-black tabular-nums sm:text-5xl"
          :class="redWon ? 'text-ok' : bluWon ? 'text-danger' : 'text-ink'"
          data-test="red-score"
        >{{ redScore }}</span>
      </div>

      <div
        class="flex items-center justify-start gap-3 border-l-4 px-4 py-4 sm:gap-5 sm:px-6"
        :class="redWon ? 'border-red bg-red-deep/50' : 'border-transparent bg-surface-800'"
      >
        <span class="text-lg font-black uppercase tracking-wider text-red sm:text-2xl">RED</span>
      </div>
    </div>

    <p class="sr-only">
      {{ bluWon ? 'BLU won' : redWon ? 'RED won' : 'No winner recorded' }}
    </p>

    <dl
      class="flex flex-wrap items-center justify-center gap-x-5 gap-y-1 border-t border-line bg-surface-900 px-3 py-2 text-sm"
    >
      <div class="flex gap-1.5">
        <dt class="text-ink-muted">Map</dt>
        <dd class="font-semibold text-ink">{{ summary.map_name || '—' }}</dd>
      </div>
      <div class="flex gap-1.5">
        <dt class="text-ink-muted">Played</dt>
        <dd class="text-ink">{{ formatDate(summary.date_played) }}</dd>
      </div>
      <div class="flex gap-1.5">
        <dt class="text-ink-muted">Duration</dt>
        <dd class="tabular-nums text-ink">{{ formatDuration(summary.duration_seconds) }}</dd>
      </div>
      <div v-if="tournamentName" class="flex gap-1.5">
        <dt class="text-ink-muted">Tournament</dt>
        <dd class="text-ink">{{ tournamentName }}</dd>
      </div>
      <div v-if="logsTfUrl" class="flex gap-1.5">
        <dt class="sr-only">Source log</dt>
        <dd>
          <a
            class="data-link font-semibold text-blu"
            :href="logsTfUrl"
            target="_blank"
            rel="noopener noreferrer"
          >logs.tf/{{ summary.source_log_id }}</a>
        </dd>
      </div>
      <div v-if="summary.ratings_ready === false" class="flex gap-1.5">
        <dd class="font-semibold text-warn">Ratings pending</dd>
      </div>
    </dl>
  </article>
</template>
