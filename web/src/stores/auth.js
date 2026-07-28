import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchAuthMe, getSteamLoginUrl } from '../api'

const TOKEN_KEY = 'tf2_auth_token'

function decodeJwtPayload(token) {
  try {
    const parts = String(token || '').split('.')
    if (parts.length < 2) return null
    const normalized = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4)
    const json = atob(padded)
    return JSON.parse(json)
  } catch {
    return null
  }
}

function loadStoredToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(loadStoredToken())
  const user = ref(null)
  const loading = ref(false)
  const error = ref('')

  const isAuthenticated = computed(() => Boolean(token.value))
  const role = computed(() => String(user.value?.role || claims.value?.role || '').toUpperCase())
  const isAdmin = computed(() => role.value === 'ADMIN')
  const steamId = computed(() => user.value?.steam_id || claims.value?.steam_id || '')
  const displayName = computed(
    () => user.value?.display_name || claims.value?.display_name || steamId.value || 'Guest',
  )
  const claims = computed(() => (token.value ? decodeJwtPayload(token.value) : null))

  function setToken(nextToken) {
    token.value = String(nextToken || '')
    try {
      if (token.value) {
        localStorage.setItem(TOKEN_KEY, token.value)
      } else {
        localStorage.removeItem(TOKEN_KEY)
      }
    } catch {
      // ignore storage failures (private mode)
    }
  }

  function logout() {
    setToken('')
    user.value = null
    error.value = ''
  }

  function beginSteamLogin() {
    window.location.assign(getSteamLoginUrl())
  }

  async function hydrateFromToken(nextToken) {
    if (!nextToken) {
      logout()
      return null
    }
    setToken(nextToken)
    return refreshProfile()
  }

  async function refreshProfile() {
    if (!token.value) {
      user.value = null
      return null
    }
    loading.value = true
    error.value = ''
    try {
      const profile = await fetchAuthMe()
      user.value = profile
      return profile
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load auth profile'
      // Expired / invalid token — clear session.
      if (String(error.value).includes('401') || String(error.value).includes('Unauthorized')) {
        logout()
      }
      return null
    } finally {
      loading.value = false
    }
  }

  async function bootstrap() {
    if (!token.value) return null
    const payload = decodeJwtPayload(token.value)
    if (payload?.exp && payload.exp * 1000 < Date.now()) {
      logout()
      return null
    }
    return refreshProfile()
  }

  return {
    token,
    user,
    loading,
    error,
    claims,
    isAuthenticated,
    isAdmin,
    role,
    steamId,
    displayName,
    setToken,
    logout,
    beginSteamLogin,
    hydrateFromToken,
    refreshProfile,
    bootstrap,
  }
})
