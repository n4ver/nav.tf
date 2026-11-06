<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { exchangeAuthCode } from '../api'
import Panel from '../components/ui/Panel.vue'
import SkeletonBlock from '../components/ui/SkeletonBlock.vue'
import StateMessage from '../components/ui/StateMessage.vue'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const message = ref('Completing Steam login…')
/** pending | error | success */
const status = ref('pending')

function fail(text) {
  status.value = 'error'
  message.value = text
}

onMounted(async () => {
  const error = typeof route.query.error === 'string' ? route.query.error : ''
  const code = typeof route.query.code === 'string' ? route.query.code : ''

  if (error) {
    fail(`Login failed: ${error}`)
    return
  }

  if (!code) {
    fail('Login failed: missing authorization code from Steam callback.')
    return
  }

  let token = ''
  try {
    const response = await exchangeAuthCode(code)
    token = typeof response?.token === 'string' ? response.token : ''
  } catch (err) {
    fail(err instanceof Error ? err.message : 'Login failed while exchanging authorization code.')
    return
  }

  if (!token) {
    fail('Login failed: authorization code exchange did not return a token.')
    return
  }

  const profile = await auth.hydrateFromToken(token)
  if (!profile) {
    fail(auth.error || 'Login failed while loading profile.')
    return
  }

  status.value = 'success'
  message.value = `Welcome, ${profile.display_name || profile.steam_id}`
  await router.replace({ name: profile.role === 'ADMIN' ? 'admin-ingest' : 'tournament' })
})
</script>

<template>
  <Panel class="mx-auto max-w-xl">
    <h1 class="text-2xl font-bold text-ink">Steam authentication</h1>

    <div v-if="status === 'pending'" class="mt-3 space-y-2" aria-busy="true" aria-label="Completing login">
      <StateMessage tone="info">{{ message }}</StateMessage>
      <SkeletonBlock :rows="1" height="h-3" />
    </div>
    <StateMessage v-else :tone="status === 'error' ? 'error' : 'success'" class="mt-3">
      {{ message }}
    </StateMessage>

    <RouterLink
      class="focus-ring mt-4 inline-block rounded text-sm font-medium text-blu transition hover:text-accent"
      to="/"
    >
      Return home
    </RouterLink>
  </Panel>
</template>
