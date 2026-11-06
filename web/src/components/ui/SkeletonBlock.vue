<script setup>
defineProps({
  rows: {
    type: Number,
    default: 1,
  },
  height: {
    type: String,
    default: 'h-10',
  },
})
</script>

<template>
  <div class="space-y-2" aria-busy="true">
    <div
      v-for="n in rows"
      :key="n"
      class="animate-pulse rounded-md bg-surface-700"
      :class="height"
    />
  </div>
</template>
