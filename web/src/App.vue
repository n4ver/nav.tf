<script setup>
import { onMounted } from 'vue'
import AppShell from './layouts/AppShell.vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()

onMounted(() => {
  auth.bootstrap()
})
</script>

<template>
  <AppShell>
    <RouterView />
  </AppShell>
</template>
