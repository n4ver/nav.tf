<script setup>
/**
 * Inline status line for empty / error / info states.
 * Errors are announced (`role="alert"`); other tones are polite status text.
 */
defineProps({
  tone: {
    type: String,
    default: 'empty',
    validator: (value) => ['empty', 'error', 'info', 'success'].includes(value),
  },
})
</script>

<template>
  <p
    class="state-message text-sm"
    :class="{
      'rounded-sm border border-danger/30 bg-danger/10 px-3 py-2 text-danger': tone === 'error',
      'text-ink-muted': tone === 'empty' || tone === 'info',
      'text-ok': tone === 'success',
    }"
    :data-tone="tone"
    :role="tone === 'error' ? 'alert' : 'status'"
  >
    <slot />
  </p>
</template>
