<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { exchangeAuthCode } from '../api'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const message = ref('Completing Steam login…')

onMounted(async () => {
  const error = typeof route.query.error === 'string' ? route.query.error : ''
  const code = typeof route.query.code === 'string' ? route.query.code : ''

  if (error) {
    message.value = `Login failed: ${error}`
    return
  }

  if (!code) {
    message.value = 'Login failed: missing authorization code from Steam callback.'
    return
  }

  let token = ''
  try {
    const response = await exchangeAuthCode(code)
    token = typeof response?.token === 'string' ? response.token : ''
  } catch (err) {
    message.value = err instanceof Error ? err.message : 'Login failed while exchanging authorization code.'
    return
  }

  if (!token) {
    message.value = 'Login failed: authorization code exchange did not return a token.'
    return
  }

  const profile = await auth.hydrateFromToken(token)
  if (!profile) {
    message.value = auth.error || 'Login failed while loading profile.'
    return
  }

  message.value = `Welcome, ${profile.display_name || profile.steam_id}`
  await router.replace({ name: profile.role === 'ADMIN' ? 'admin-dashboard' : 'tournament' })
})
</script>

<template>
  <div class="page-wrap">
    <main class="panel">
      <h1>Steam authentication</h1>
      <p class="status-msg">{{ message }}</p>
      <RouterLink class="inline-link" to="/">Return home</RouterLink>
    </main>
  </div>
</template>
