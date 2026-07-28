import { computed } from 'vue'
import { useAuthStore } from '../stores/auth'

/**
 * Role-gated UI helper.
 * @param {string | string[]} requiredRole - e.g. 'ADMIN' or ['ADMIN']
 */
export function useCan(requiredRole) {
  const auth = useAuthStore()
  const required = Array.isArray(requiredRole)
    ? requiredRole.map((role) => String(role).toUpperCase())
    : [String(requiredRole || '').toUpperCase()]

  const allowed = computed(() => {
    if (!auth.isAuthenticated) return false
    if (!required.length || required.includes('')) return auth.isAuthenticated
    return required.includes(auth.role)
  })

  return {
    allowed,
    isAdmin: computed(() => auth.isAdmin),
    isAuthenticated: computed(() => auth.isAuthenticated),
    role: computed(() => auth.role),
  }
}
