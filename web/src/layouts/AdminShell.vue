<script setup>
import { storeToRefs } from 'pinia'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const { displayName, steamId } = storeToRefs(useAuthStore())

const links = [
  { to: '/admin/ingest', name: 'admin-ingest', label: 'Ingest' },
  { to: '/admin/events', name: 'admin-events', label: 'Events' },
  { to: '/admin/tournaments', name: 'admin-tournaments', label: 'Tournaments' },
  { to: '/admin/matches', name: 'admin-matches', label: 'Matches' },
  { to: '/admin/players', name: 'admin-players', label: 'Players' },
]
</script>

<template>
  <div class="space-y-3">
    <header class="flex flex-wrap items-baseline justify-between gap-2">
      <h1 class="text-lg font-bold">Admin</h1>
      <p v-if="steamId" class="text-xs text-ink-muted" data-test="admin-identity">
        Signed in as <span class="font-semibold text-ink">{{ displayName }}</span>
        <span class="font-mono">({{ steamId }})</span>
      </p>
    </header>

    <nav class="flex flex-wrap gap-1" aria-label="Admin sections">
      <RouterLink
        v-for="link in links"
        :key="link.name"
        :to="link.to"
        class="tab"
        :class="{ 'tab-active': route.name === link.name }"
        :aria-current="route.name === link.name ? 'page' : undefined"
      >
        {{ link.label }}
      </RouterLink>
    </nav>

    <RouterView />
  </div>
</template>
