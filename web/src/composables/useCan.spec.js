import { describe, expect, it, vi } from 'vitest'
import { createTestingPinia } from '@pinia/testing'
import { useCan } from './useCan'

vi.mock('../api', () => ({
  fetchAuthMe: vi.fn(),
  getSteamLoginUrl: vi.fn(() => '/login'),
}))

function withAuth(auth) {
  createTestingPinia({ createSpy: vi.fn, initialState: { auth } })
}

describe('useCan', () => {
  describe('when signed out', () => {
    it('denies every role', () => {
      // Arrange
      withAuth({ token: '', user: null })

      // Act
      const { allowed, isAuthenticated } = useCan('ADMIN')

      // Assert
      expect(allowed.value).toBe(false)
      expect(isAuthenticated.value).toBe(false)
    })

    it('denies the "any signed-in user" check too', () => {
      withAuth({ token: '', user: null })

      expect(useCan('').allowed.value).toBe(false)
    })
  })

  describe('when signed in', () => {
    it('allows a matching role case-insensitively', () => {
      // Arrange
      withAuth({ token: 'tok', user: { role: 'admin', steam_id: '1' } })

      // Act
      const { allowed, isAdmin, role } = useCan('Admin')

      // Assert
      expect(allowed.value).toBe(true)
      expect(isAdmin.value).toBe(true)
      expect(role.value).toBe('ADMIN')
    })

    it('denies a role the user does not have', () => {
      withAuth({ token: 'tok', user: { role: 'USER', steam_id: '1' } })

      expect(useCan('ADMIN').allowed.value).toBe(false)
    })

    it('accepts any role from an array', () => {
      withAuth({ token: 'tok', user: { role: 'MODERATOR', steam_id: '1' } })

      expect(useCan(['ADMIN', 'moderator']).allowed.value).toBe(true)
    })

    it('treats an empty role as "any authenticated user"', () => {
      withAuth({ token: 'tok', user: { role: 'USER', steam_id: '1' } })

      expect(useCan().allowed.value).toBe(true)
    })
  })
})
