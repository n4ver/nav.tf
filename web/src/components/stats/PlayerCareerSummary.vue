<script setup>
import { computed } from 'vue'
import { formatNumber } from '../../utils/format'
import { formatRating, ratingTone } from '../../utils/rating'
import { createSteamURL, formatPlayerLabel } from '../../utils/steam'

/** Player profile header: identity, headline rating, and career stat strip. */
const props = defineProps({
  stats: {
    type: Object,
    required: true,
  },
})

const steamUrl = computed(() => createSteamURL(props.stats.steam_id))

const kdRatio = computed(() => {
  const deaths = Number(props.stats.total_deaths) || 0
  const kills = Number(props.stats.total_kills) || 0
  return deaths ? (kills / deaths).toFixed(2) : kills ? '∞' : '—'
})

const kpis = computed(() => [
  { label: 'Maps played', value: props.stats.matches_played ?? 0 },
  { label: 'K/D ratio', value: kdRatio.value },
  { label: 'Kills', value: props.stats.total_kills ?? 0 },
  { label: 'Deaths', value: props.stats.total_deaths ?? 0 },
  { label: 'Assists', value: props.stats.total_assists ?? 0 },
  { label: 'Damage / min', value: formatNumber(props.stats.average_damage_per_minute, 1) },
  { label: 'Healing', value: props.stats.total_healing_done ?? 0 },
])
</script>

<template>
  <section class="overflow-hidden rounded-sm border border-line bg-surface-800" data-test="player-summary">
    <div class="flex flex-wrap items-center justify-between gap-4 px-4 py-3">
      <div class="min-w-0">
        <h1 class="truncate text-2xl font-bold text-ink">{{ formatPlayerLabel(stats) }}</h1>
        <p class="mt-0.5 flex flex-wrap items-center gap-x-3 text-sm text-ink-muted">
          <span class="font-mono text-xs">{{ stats.steam_id }}</span>
          <a
            v-if="steamUrl"
            class="data-link font-semibold text-blu"
            :href="steamUrl"
            target="_blank"
            rel="noopener noreferrer"
          >Steam profile</a>
        </p>
      </div>
      <div class="text-right">
        <p class="text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Average rating</p>
        <p class="text-4xl leading-none">
          <span class="rating-chip" :class="`tone-${ratingTone(stats.average_rating)}`">
            {{ formatRating(stats.average_rating, 2) }}
          </span>
        </p>
      </div>
    </div>

    <dl class="grid grid-cols-2 border-t border-line bg-surface-900 sm:grid-cols-4 lg:grid-cols-7">
      <div
        v-for="kpi in kpis"
        :key="kpi.label"
        class="border-b border-r border-line px-3 py-2 lg:border-b-0"
      >
        <dt class="text-[0.7rem] text-ink-muted">{{ kpi.label }}</dt>
        <dd class="text-base font-bold tabular-nums text-ink">{{ kpi.value }}</dd>
      </div>
    </dl>
  </section>
</template>
