import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AuthCallbackView from './AuthCallbackView.vue'
import { useAuthStore } from '../stores/auth'
import { createTestRouter } from '../test/helpers'
import * as api from '../api'

vi.mock('../api', () => ({
  exchangeAuthCode: vi.fn(),
  fetchAuthMe: vi.fn(),
  getSteamLoginUrl: vi.fn(() => '/login'),
}))

async function mountCallback(query, { profile = null } = {}) {
  const router = createTestRouter()
  await router.push({ name: 'auth-callback', query })
  await router.isReady()
  const pinia = createTestingPinia({ createSpy: vi.fn })
  const auth = useAuthStore(pinia)
  auth.hydrateFromToken.mockResolvedValue(profile)
  const wrapper = mount(AuthCallbackView, { global: { plugins: [router, pinia] } })
  return { wrapper, router, auth }
}

describe('AuthCallbackView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('errors', () => {
    it('reports an error passed back by the command service', async () => {
      const { wrapper } = await mountCallback({ error: 'openid_invalid' })
      await flushPromises()

      expect(wrapper.get('[role="alert"]').text()).toBe('Login failed: openid_invalid')
      expect(api.exchangeAuthCode).not.toHaveBeenCalled()
    })

    it('reports a missing code', async () => {
      const { wrapper } = await mountCallback({})
      await flushPromises()

      expect(wrapper.get('[role="alert"]').text()).toContain('missing authorization code')
    })

    it('reports a failed code exchange', async () => {
      api.exchangeAuthCode.mockRejectedValue(new Error('400 Bad Request'))

      const { wrapper } = await mountCallback({ code: 'abc' })
      await flushPromises()

      expect(wrapper.get('[role="alert"]').text()).toBe('400 Bad Request')
    })
  })

  it('reports a profile load failure after a successful exchange', async () => {
    api.exchangeAuthCode.mockResolvedValue({ token: 'jwt' })

    const { wrapper } = await mountCallback({ code: 'abc' }, { profile: null })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('Login failed while loading profile.')
  })

  describe('pending', () => {
    it('shows a busy state while the code is exchanged', async () => {
      api.exchangeAuthCode.mockReturnValue(new Promise(() => {}))

      const { wrapper } = await mountCallback({ code: 'abc' })
      await flushPromises()

      expect(wrapper.find('[aria-label="Completing login"]').exists()).toBe(true)
    })
  })

  describe('success', () => {
    it('stores the token and sends admins to the admin area', async () => {
      // Arrange
      api.exchangeAuthCode.mockResolvedValue({ token: 'jwt' })
      const { router, auth } = await mountCallback(
        { code: 'abc' },
        { profile: { steam_id: '1', role: 'ADMIN', display_name: 'Boss' } },
      )

      // Act
      await flushPromises()

      // Assert
      expect(api.exchangeAuthCode).toHaveBeenCalledWith('abc')
      expect(auth.hydrateFromToken).toHaveBeenCalledWith('jwt')
      expect(router.currentRoute.value.name).toBe('admin-ingest')
    })

    it('sends regular users to the tournament dashboard', async () => {
      api.exchangeAuthCode.mockResolvedValue({ token: 'jwt' })
      const { router } = await mountCallback({ code: 'abc' }, { profile: { steam_id: '2', role: 'USER' } })

      await flushPromises()

      expect(router.currentRoute.value.name).toBe('tournament')
    })
  })
})
