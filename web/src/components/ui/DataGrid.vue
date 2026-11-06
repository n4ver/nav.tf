<script setup>
import { computed, ref, watch } from 'vue'
import SkeletonBlock from '../ui/SkeletonBlock.vue'

const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
  columns: {
    type: Array,
    required: true,
  },
  rowKey: {
    type: [String, Function],
    default: 'id',
  },
  loading: {
    type: Boolean,
    default: false,
  },
  emptyMessage: {
    type: String,
    default: 'No rows to display.',
  },
  defaultSortKey: {
    type: String,
    default: '',
  },
  defaultSortDir: {
    type: String,
    default: 'desc',
  },
  rowClass: {
    type: Function,
    default: null,
  },
  onRowClick: {
    type: Function,
    default: null,
  },
  /**
   * When true, the table uses a fixed layout that fills its container (column `width`s apply).
   * A compact min-width still kicks in on narrow screens so it scrolls instead of crushing.
   */
  fitContainer: {
    type: Boolean,
    default: false,
  },
})

const sortKey = ref(props.defaultSortKey || '')
const sortDir = ref(props.defaultSortDir === 'asc' ? 'asc' : 'desc')

watch(
  () => [props.defaultSortKey, props.defaultSortDir],
  ([key, dir]) => {
    if (key) sortKey.value = key
    if (dir) sortDir.value = dir === 'asc' ? 'asc' : 'desc'
  },
)

/**
 * Column priority: `hideBelow: 'md'` hides a secondary column on phones so the
 * key stats (player, +/-, rating) fit without sideways scrolling.
 */
function isOptional(column) {
  return column.hideBelow === 'md'
}

function minWidthFor(count) {
  // Compact floor for fixed-layout tables; on wide screens they still fill the container.
  if (props.fitContainer) return `${count * 52}px`
  // Dense stat tables: ~64px per column keeps numbers readable; narrower screens scroll.
  return `${Math.max(560, count * 64)}px`
}

const tableStyle = computed(() => {
  const all = props.columns?.length || 0
  const core = props.columns.filter((column) => !isOptional(column)).length
  return {
    '--grid-min': core === all ? minWidthFor(all) : `${core * 56}px`,
    '--grid-min-md': minWidthFor(all),
  }
})

function visibilityClass(column) {
  return isOptional(column) ? 'hidden md:table-cell' : ''
}

function resolveKey(row, index) {
  if (typeof props.rowKey === 'function') {
    return props.rowKey(row, index)
  }
  return row?.[props.rowKey] ?? index
}

function cellValue(row, column) {
  if (typeof column.value === 'function') {
    return column.value(row)
  }
  const key = column.key
  if (!key) return undefined
  return key.split('.').reduce((acc, part) => (acc == null ? acc : acc[part]), row)
}

function displayValue(row, column) {
  const raw = cellValue(row, column)
  if (typeof column.format === 'function') {
    return column.format(raw, row)
  }
  if (raw == null || raw === '') return '—'
  return raw
}

/** True when a stat cell represents zero (not empty/null). */
function isZeroStat(row, column) {
  const raw = cellValue(row, column)
  const displayed = displayValue(row, column)

  if (displayed === '—' || displayed == null || displayed === '') {
    return false
  }

  if (typeof raw === 'number') {
    return raw === 0
  }

  if (typeof raw === 'string' && /^\d+\/\d+\/\d+$/.test(raw)) {
    return raw === '0/0/0'
  }

  if (displayed === '0/0/0') {
    return true
  }

  const asString = String(displayed).trim()
  if (/^0(\.0+)?%?$/.test(asString)) {
    return true
  }

  if (typeof raw === 'string' || typeof raw === 'number') {
    const n = Number(raw)
    if (!Number.isNaN(n)) {
      return n === 0
    }
  }

  return false
}

function cellClass(row, column) {
  return [
    alignClass(column),
    visibilityClass(column),
    // `truncate: true` ellipsizes long names on phones so numeric columns stay visible.
    column.truncate ? 'max-w-[8.5rem] overflow-hidden text-ellipsis md:max-w-none' : '',
    column.align === 'right' || column.numeric ? 'tabular-nums' : '',
    column.cellClass,
    isZeroStat(row, column) ? 'text-ink-muted/50' : '',
  ]
}

function toggleSort(column) {
  if (!column.sortable) return
  if (sortKey.value === column.key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = column.key
    sortDir.value = 'desc'
  }
}

const sortedRows = computed(() => {
  const list = [...props.rows]
  if (!sortKey.value) return list
  const column = props.columns.find((c) => c.key === sortKey.value)
  if (!column) return list

  const dir = sortDir.value === 'asc' ? 1 : -1
  list.sort((a, b) => {
    const left = cellValue(a, column)
    const right = cellValue(b, column)
    if (typeof column.sortValue === 'function') {
      const cmp = column.sortValue(a, b)
      return cmp * dir
    }
    if (typeof left === 'number' && typeof right === 'number') {
      return (left - right) * dir
    }
    return String(left ?? '').localeCompare(String(right ?? ''), undefined, { numeric: true }) * dir
  })
  return list
})

function ariaSort(column) {
  if (!column.sortable) return undefined
  if (sortKey.value !== column.key) return 'none'
  return sortDir.value === 'asc' ? 'ascending' : 'descending'
}

function alignClass(column) {
  if (column.align === 'right') return 'text-right'
  if (column.align === 'center') return 'text-center'
  return 'text-left'
}
</script>

<template>
  <div class="data-grid">
    <div v-if="loading" class="p-3" aria-busy="true" aria-label="Loading table">
      <SkeletonBlock :rows="5" />
    </div>

    <div v-else-if="!rows.length" class="px-3 py-4 text-sm text-ink-muted" role="status">
      {{ emptyMessage }}
    </div>

    <div v-else class="overflow-x-auto">
      <table
        class="w-full min-w-(--grid-min) border-collapse text-sm md:min-w-(--grid-min-md)"
        :class="fitContainer ? 'table-fixed' : ''"
        :style="tableStyle"
      >
        <colgroup v-if="fitContainer">
          <col
            v-for="column in columns"
            :key="column.key"
            :class="isOptional(column) ? 'hidden md:table-column' : ''"
            :style="column.width ? { width: column.width } : undefined"
          />
        </colgroup>
        <thead class="bg-surface-900">
          <tr>
            <th
              v-for="column in columns"
              :key="column.key"
              scope="col"
              class="whitespace-nowrap border-b border-line py-1.5 text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted"
              :class="['px-2 md:px-2.5', alignClass(column), visibilityClass(column), column.headerClass]"
              :aria-sort="ariaSort(column)"
            >
              <button
                v-if="column.sortable"
                type="button"
                class="focus-ring inline-flex items-center gap-1 rounded-sm uppercase tracking-wide hover:text-ink"
                @click="toggleSort(column)"
              >
                {{ column.label }}
                <span v-if="sortKey === column.key" class="font-mono text-accent" aria-hidden="true">
                  {{ sortDir === 'asc' ? '↑' : '↓' }}
                </span>
              </button>
              <span v-else>{{ column.label }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, index) in sortedRows"
            :key="resolveKey(row, index)"
            class="border-b border-line last:border-b-0 even:bg-surface-900/40 hover:bg-surface-700"
            :class="[
              onRowClick ? 'focus-ring cursor-pointer' : '',
              rowClass ? rowClass(row, index) : '',
            ]"
            :tabindex="onRowClick ? 0 : undefined"
            @click="onRowClick ? onRowClick(row, index) : undefined"
            @keydown.enter.self="onRowClick ? onRowClick(row, index) : undefined"
          >
            <td
              v-for="column in columns"
              :key="`${resolveKey(row, index)}-${column.key}`"
              class="whitespace-nowrap px-2 py-1.5 text-[0.8125rem] text-ink md:px-2.5"
              :class="cellClass(row, column)"
            >
              <slot
                :name="`cell-${column.key}`"
                :row="row"
                :value="cellValue(row, column)"
                :muted="isZeroStat(row, column)"
              >
                {{ displayValue(row, column) }}
              </slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
