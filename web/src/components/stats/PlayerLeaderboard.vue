<script setup>
import { computed } from 'vue'
import DataGrid from '../ui/DataGrid.vue'
import StateMessage from '../ui/StateMessage.vue'
import { TF2_CLASSES, formatNumber, playerPath } from '../../utils/format'
import { formatRating, ratingTone } from '../../utils/rating'
import { formatPlayerLabel } from '../../utils/steam'

/**
 * Ranked player table with a one-click class filter.
 * Shared by the tournament home and event pages; `v-model:class-filter` drives refetches.
 */
const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
  emptyMessage: {
    type: String,
    default: 'No players rated for this filter yet.',
  },
  classFilter: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:classFilter'])

const columns = [
  { key: 'rank', label: '#', sortable: true, align: 'right', numeric: true },
  { key: 'player', label: 'Player', sortable: true, truncate: true, value: (row) => formatPlayerLabel(row) },
  { key: 'primary_class', label: 'Class', sortable: true, hideBelow: 'md' },
  { key: 'matches_played', label: 'Maps', sortable: true, align: 'right', numeric: true, hideBelow: 'md' },
  {
    key: 'kd',
    label: 'K-D',
    sortable: true,
    align: 'right',
    numeric: true,
    value: (row) => `${Number(row.total_kills) || 0}-${Number(row.total_deaths) || 0}`,
    sortValue: (a, b) => (Number(a.total_kills) || 0) - (Number(b.total_kills) || 0),
  },
  {
    key: 'diff',
    label: '+/-',
    sortable: true,
    align: 'right',
    numeric: true,
    value: (row) => (Number(row.total_kills) || 0) - (Number(row.total_deaths) || 0),
  },
  {
    key: 'average_damage_per_minute',
    hideBelow: 'md',
    label: 'DPM',
    sortable: true,
    align: 'right',
    numeric: true,
    format: (v) => formatNumber(v, 1),
  },
  { key: 'average_rating', label: 'Rating', sortable: true, align: 'right', numeric: true },
]

/** Rank by the API's order (rating desc) so # stays stable while re-sorting columns. */
const rankedRows = computed(() => props.rows.map((row, index) => ({ ...row, rank: index + 1 })))

function shortClass(name) {
  return name === 'heavyweapons' ? 'heavy' : name
}
</script>

<template>
  <div>
    <div class="flex flex-wrap gap-1 border-b border-line px-3 py-2" role="group" aria-label="Class filter">
      <button
        type="button"
        class="tab"
        :class="{ 'tab-active': classFilter === '' }"
        :aria-pressed="classFilter === ''"
        @click="emit('update:classFilter', '')"
      >
        All
      </button>
      <button
        v-for="name in TF2_CLASSES"
        :key="name"
        type="button"
        class="tab capitalize"
        :class="{ 'tab-active': classFilter === name }"
        :aria-pressed="classFilter === name"
        :data-test="`class-${name}`"
        @click="emit('update:classFilter', name)"
      >
        {{ shortClass(name) }}
      </button>
    </div>

    <StateMessage v-if="error" tone="error" class="m-3">{{ error }}</StateMessage>
    <DataGrid
      v-else
      :rows="rankedRows"
      :columns="columns"
      row-key="steam_id"
      :loading="loading"
      :empty-message="emptyMessage"
      default-sort-key="rank"
      default-sort-dir="asc"
    >
      <template #cell-player="{ row }">
        <RouterLink class="data-link font-semibold" :to="playerPath(row.steam_id)">
          {{ formatPlayerLabel(row) }}
        </RouterLink>
      </template>
      <template #cell-primary_class="{ value }">
        <span class="capitalize">{{ value || '—' }}</span>
      </template>
      <template #cell-diff="{ value }">
        <span :class="value > 0 ? 'text-ok' : value < 0 ? 'text-danger' : 'text-ink-muted'">
          {{ value > 0 ? `+${value}` : value }}
        </span>
      </template>
      <template #cell-average_rating="{ row }">
        <span class="rating-chip" :class="`tone-${ratingTone(row.average_rating)}`">
          {{ formatRating(row.average_rating, 2) }}
        </span>
      </template>
    </DataGrid>
  </div>
</template>
