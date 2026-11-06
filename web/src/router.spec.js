import { describe, expect, it, vi } from 'vitest'
import { createTestingPinia } from '@pinia/testing'
import router, { authGuard } from './router'
import { useAuthStore } from './stores/auth'

vi.mock('./api', () => ({
  fetchAuthMe: vi.fn(),
  getSteamLoginUrl: vi.fn(() => '/login'),
  getQueryBaseUrl: vi.fn(() => '/api/query'),
}))

function setupAuth(state) {
  createTestingPinia({ createSpy: vi.fn, initialState: { auth: state } })
  return useAuthStore()
}

const publicRoute = { name: 'tournament', meta: {} }
const adminRoute = { name: 'admin-ingest', meta: { requiresAuth: true, requiresAdmin: true } }

describe('authGuard', () => {
  describe('session bootstrap', () => {
    it('bootstraps the user when a token exists without a loaded profile', async () => {
      // Arrange
      const auth = setupAuth({ token: 'tok', user: null })

      // Act
      await authGuard(publicRoute)

      // Assert
      expect(auth.bootstrap).toHaveBeenCalledTimes(1)
    })

    it('skips bootstrap when there is no token', async () => {
      const auth = setupAuth({ token: '', user: null })

      await authGuard(publicRoute)

      expect(auth.bootstrap).not.toHaveBeenCalled()
    })
  })

  describe('public routes', () => {
    it('allows anonymous navigation', async () => {
      setupAuth({ token: '', user: null })

      await expect(authGuard(publicRoute)).resolves.toBe(true)
    })
  })

  describe('admin routes', () => {
    it('starts Steam login and cancels navigation for anonymous users', async () => {
      // Arrange
      const auth = setupAuth({ token: '', user: null })

      // Act
      const result = await authGuard(adminRoute)

      // Assert
      expect(result).toBe(false)
      expect(auth.beginSteamLogin).toHaveBeenCalledTimes(1)
    })

    it('redirects signed-in non-admins to the tournament dashboard', async () => {
      const auth = setupAuth({ token: 'tok', user: { role: 'USER', steam_id: '1' } })

      const result = await authGuard(adminRoute)

      expect(result).toEqual({ name: 'tournament' })
      expect(auth.beginSteamLogin).not.toHaveBeenCalled()
    })

    it('allows admins through', async () => {
      setupAuth({ token: 'tok', user: { role: 'ADMIN', steam_id: '1' } })

      await expect(authGuard(adminRoute)).resolves.toBe(true)
    })
  })
})

describe('route table', () => {
  it('marks every /admin child as admin-only via the parent record', () => {
    const resolved = router.resolve('/admin/players')

    expect(resolved.name).toBe('admin-players')
    expect(resolved.matched.some((record) => record.meta.requiresAdmin)).toBe(true)
  })

  it('accepts the list routes without params', () => {
    expect(router.resolve('/event').name).toBe('event')
    expect(router.resolve('/match').name).toBe('match-stats')
    expect(router.resolve('/player').name).toBe('player-stats')
  })

  it('redirects the legacy admin dashboard and match-log URLs', () => {
    const dashboard = router.resolve('/admin/dashboard')
    const legacyLog = router.resolve('/match-log/123')

    expect(dashboard.matched[0].redirect).toEqual({ name: 'admin-ingest' })
    expect(typeof legacyLog.matched[0].redirect).toBe('function')
    expect(legacyLog.matched[0].redirect({ params: { logId: '123' } })).toEqual({
      name: 'match-stats',
      params: { matchId: '123' },
    })
  })
})
