<script setup>
import { computed } from 'vue'
import SkeletonBlock from '../ui/SkeletonBlock.vue'
import StateMessage from '../ui/StateMessage.vue'
import { formatMinutes, matchPath } from '../../utils/format'

/**
 * Results list: one clickable row per match, BLU score : score RED.
 * `groupByDay` adds day headers (results page); `compact` is the narrow sidebar variant.
 */
const props = defineProps({
  matches: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  emptyMessage: {
    type: String,
    default: 'No matches yet.',
  },
  groupByDay: {
    type: Boolean,
    default: false,
  },
  compact: {
    type: Boolean,
    default: false,
  },
  /** Optional tournament_id → name map shown on full rows. */
  tournamentNames: {
    type: Object,
    default: () => ({}),
  },
})

function dayKey(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Unknown date' : date.toDateString()
}

function dayLabel(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown date'
  return date.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
}

function timeLabel(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

const groups = computed(() => {
  const sorted = [...props.matches].sort(
    (a, b) => new Date(b.date_played || 0) - new Date(a.date_played || 0),
  )
  if (!props.groupByDay) return [{ key: 'all', label: '', rows: sorted }]
  const out = []
  for (const row of sorted) {
    const key = dayKey(row.date_played)
    let group = out.find((g) => g.key === key)
    if (!group) {
      group = { key, label: dayLabel(row.date_played), rows: [] }
      out.push(group)
    }
    group.rows.push(row)
  }
  return out
})

function winner(row) {
  return String(row.winning_team || '').toLowerCase()
}

function scoreClass(row, side) {
  const w = winner(row)
  if (!w) return 'text-ink'
  return w === side ? 'text-ok' : 'text-danger'
}

function scoreOf(row, side) {
  const n = Number(row[`${side}_score`])
  return Number.isFinite(n) ? n : '–'
}
</script>

<template>
  <div v-if="loading" class="p-3" aria-busy="true" aria-label="Loading matches">
    <SkeletonBlock :rows="compact ? 6 : 8" :height="compact ? 'h-9' : 'h-8'" />
  </div>

  <StateMessage v-else-if="!matches.length" class="p-3">{{ emptyMessage }}</StateMessage>

  <div v-else data-test="result-list">
    <section v-for="group in groups" :key="group.key">
      <h3
        v-if="group.label"
        class="border-b border-line bg-surface-900 px-3 py-1.5 text-xs font-bold text-ink-muted"
      >
        {{ group.label }}
      </h3>
      <ul class="list-none">
        <li v-for="row in group.rows" :key="row.match_id" class="border-b border-line last:border-b-0">
          <!-- Compact: sidebar widget -->
          <RouterLink
            v-if="compact"
            :to="matchPath(row.match_id)"
            class="focus-ring block px-3 py-1.5 hover:bg-surface-700"
            data-test="result-row"
          >
            <span class="flex items-center justify-between gap-2 text-sm">
              <span class="font-bold text-blu">BLU</span>
              <span class="font-bold tabular-nums">
                <span :class="scoreClass(row, 'blu')">{{ scoreOf(row, 'blu') }}</span>
                <span class="px-1 text-ink-muted">:</span>
                <span :class="scoreClass(row, 'red')">{{ scoreOf(row, 'red') }}</span>
              </span>
              <span class="font-bold text-red">RED</span>
            </span>
            <span class="mt-0.5 flex justify-between gap-2 text-[0.7rem] text-ink-muted">
              <span class="truncate">{{ row.map_name || '—' }}</span>
              <span class="shrink-0 tabular-nums">{{ formatMinutes(row.duration_seconds) }}</span>
            </span>
          </RouterLink>

          <!-- Full: results page row -->
          <RouterLink
            v-else
            :to="matchPath(row.match_id)"
            class="focus-ring grid grid-cols-[3.5rem_1fr_auto_1fr] items-center gap-2 px-3 py-2 text-sm hover:bg-surface-700 sm:grid-cols-[3.5rem_5rem_auto_5rem_1fr_auto]"
            data-test="result-row"
          >
            <span class="tabular-nums text-xs text-ink-muted">{{ timeLabel(row.date_played) }}</span>
            <span class="text-right font-bold text-blu">BLU</span>
            <span class="min-w-[4.5rem] text-center font-bold tabular-nums">
              <span :class="scoreClass(row, 'blu')">{{ scoreOf(row, 'blu') }}</span>
              <span class="px-1 text-ink-muted">-</span>
              <span :class="scoreClass(row, 'red')">{{ scoreOf(row, 'red') }}</span>
            </span>
            <span class="font-bold text-red">RED</span>
            <span class="col-span-4 truncate text-xs text-ink-muted sm:col-span-1 sm:text-sm">
              <span class="text-ink">{{ row.map_name || '—' }}</span>
              <span v-if="tournamentNames[row.tournament_id]"> · {{ tournamentNames[row.tournament_id] }}</span>
            </span>
            <span class="hidden tabular-nums text-xs text-ink-muted sm:inline">
              {{ formatMinutes(row.duration_seconds) }}
            </span>
          </RouterLink>
        </li>
      </ul>
    </section>
  </div>
</template>
