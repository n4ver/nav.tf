<script setup>
/**
 * Flat content box with an optional headline bar.
 *   <Panel title="Results">…</Panel>
 *   <Panel title="Leaderboard" flush><template #actions>…</template><DataGrid … /></Panel>
 * `flush` drops body padding so tables/lists run edge to edge.
 */
defineProps({
  title: {
    type: String,
    default: '',
  },
  as: {
    type: String,
    default: 'section',
  },
  flush: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <component :is="as" class="panel overflow-hidden rounded-sm border border-line bg-surface-800">
    <header
      v-if="title || $slots.title || $slots.actions"
      class="flex min-h-9 flex-wrap items-center justify-between gap-2 border-b border-line bg-surface-900 px-3 py-1.5"
    >
      <h2 class="text-[0.8rem] font-bold uppercase tracking-wide text-ink">
        <slot name="title">{{ title }}</slot>
      </h2>
      <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
        <slot name="actions" />
      </div>
    </header>
    <div :class="flush ? '' : 'p-3'">
      <slot />
    </div>
  </component>
</template>
