<script setup>
import { onMounted, ref } from 'vue'
import AppTopNav from '../components/layout/AppTopNav.vue'
import { fetchQueryHealth } from '../api'

/** null = checking, true = up, false = down */
const apiUp = ref(null)

onMounted(async () => {
  try {
    const health = await fetchQueryHealth()
    apiUp.value = String(health?.status || '').toLowerCase() === 'ok'
  } catch {
    apiUp.value = false
  }
})
</script>

<template>
  <div class="flex min-h-svh flex-col bg-surface-950 text-ink">
    <a
      href="#main-content"
      class="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[60] focus:rounded-sm focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:font-bold focus:text-white"
    >
      Skip to content
    </a>

    <AppTopNav />

    <main id="main-content" class="flex-1" tabindex="-1">
      <div class="mx-auto w-full max-w-[1400px] px-3 py-4 lg:px-4">
        <slot />
      </div>
    </main>

    <footer class="border-t border-line bg-surface-900">
      <div
        class="mx-auto flex w-full max-w-[1400px] flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs text-ink-muted lg:px-4"
      >
        <span>nav.tf · ratings use a 0–2 band where 1.000 is the class average</span>
        <span class="inline-flex items-center gap-1.5" data-test="api-status" role="status">
          <span
            class="h-2 w-2 rounded-full"
            :class="apiUp === null ? 'bg-ink-muted' : apiUp ? 'bg-ok' : 'bg-danger'"
            aria-hidden="true"
          />
          {{ apiUp === null ? 'Checking API…' : apiUp ? 'API online' : 'API unavailable' }}
        </span>
      </div>
    </footer>
  </div>
</template>
