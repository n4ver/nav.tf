import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AppTopNav from './AppTopNav.vue'
import { useAuthStore } from '../../stores/auth'
import { createTestRouter } from '../../test/helpers'
import * as api from '../../api'

vi.mock('../../api', () => ({
  fetchAuthMe: vi.fn(),
  getSteamLoginUrl: vi.fn(() => '/login'),
  searchQuery: vi.fn(),
}))

const ADMIN = { token: 'tok', user: { role: 'ADMIN', steam_id: '1', display_name: 'Boss' } }
const USER = { token: 'tok', user: { role: 'USER', steam_id: '2', display_name: 'Pleb' } }
const ANON = { token: '', user: null }

let wrapper

async function mountNav({ path = '/', auth = ANON } = {}) {
  const router = createTestRouter()
  await router.push(path)
  await router.isReady()
  wrapper = mount(AppTopNav, {
    attachTo: document.body,
    global: {
      plugins: [router, createTestingPinia({ createSpy: vi.fn, initialState: { auth } })],
    },
  })
  return { wrapper, router, auth: useAuthStore() }
}

const toggle = (w) => w.get('[data-test="menu-toggle"]')

describe('AppTopNav', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    wrapper?.unmount()
  })

  describe('brand', () => {
    it('shows the nav.tf wordmark without an icon', async () => {
      const { wrapper } = await mountNav()

      const brand = wrapper.get('[data-test="brand"]')
      expect(brand.text()).toBe('nav.tf')
      expect(brand.attributes('aria-label')).toBe('nav.tf home')
      expect(brand.findAll('span')).toHaveLength(1)
    })
  })

  describe('active link', () => {
    it('marks only the current section with aria-current="page"', async () => {
      // Arrange / Act
      const { wrapper } = await mountNav({ path: '/match/abc' })

      // Assert
      const current = wrapper.findAll('nav[aria-label="Primary"] [aria-current="page"]')
      expect(current).toHaveLength(1)
      expect(current[0].attributes('data-test')).toBe('nav-match-stats')
    })

    it('does not mark Home active on /event', async () => {
      const { wrapper } = await mountNav({ path: '/event' })

      expect(wrapper.get('[data-test="nav-event"]').attributes('aria-current')).toBe('page')
      expect(wrapper.get('[data-test="nav-tournament"]').attributes('aria-current')).toBeUndefined()
    })

    it('marks Admin active for any /admin child route', async () => {
      const { wrapper } = await mountNav({ path: '/admin/players', auth: ADMIN })

      expect(wrapper.get('[data-test="nav-admin"]').attributes('aria-current')).toBe('page')
    })
  })

  describe('admin link visibility', () => {
    it.each([
      ['anonymous visitors', ANON, false],
      ['signed-in non-admins', USER, false],
      ['admins', ADMIN, true],
    ])('for %s → %s', async (_label, auth, visible) => {
      const { wrapper } = await mountNav({ auth })

      expect(wrapper.find('[data-test="nav-admin"]').exists()).toBe(visible)
    })
  })

  describe('account controls', () => {
    it('starts Steam login when signed out', async () => {
      // Arrange
      const { wrapper, auth } = await mountNav()

      // Act
      await wrapper.findAll('button').find((b) => b.text() === 'Sign in through Steam').trigger('click')

      // Assert
      expect(auth.beginSteamLogin).toHaveBeenCalled()
    })

    it('shows the user and logs out when signed in', async () => {
      const { wrapper, auth } = await mountNav({ auth: USER })

      expect(wrapper.text()).toContain('Pleb')
      await wrapper.findAll('button').find((b) => b.text() === 'Log out').trigger('click')

      expect(auth.logout).toHaveBeenCalled()
    })
  })

  describe('mobile menu', () => {
    it('toggles with aria-expanded and aria-controls', async () => {
      // Arrange
      const { wrapper } = await mountNav()
      expect(toggle(wrapper).attributes('aria-expanded')).toBe('false')
      expect(toggle(wrapper).attributes('aria-controls')).toBe('mobile-nav')

      // Act
      await toggle(wrapper).trigger('click')

      // Assert
      expect(toggle(wrapper).attributes('aria-expanded')).toBe('true')
      expect(wrapper.get('[data-test="mobile-nav"]').isVisible()).toBe(true)
    })

    it('closes on Escape', async () => {
      const { wrapper } = await mountNav()
      await toggle(wrapper).trigger('click')

      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
      await wrapper.vm.$nextTick()

      expect(toggle(wrapper).attributes('aria-expanded')).toBe('false')
    })

    it('closes after navigating', async () => {
      const { wrapper, router } = await mountNav()
      await toggle(wrapper).trigger('click')

      await router.push('/player')
      await flushPromises()

      expect(toggle(wrapper).attributes('aria-expanded')).toBe('false')
    })
  })

  describe('search', () => {
    async function search(w, query) {
      await w.get('input[type="search"]').setValue(query)
      await w.get('form[role="search"]').trigger('submit.prevent')
      await flushPromises()
    }

    it('asks for input when empty', async () => {
      const { wrapper } = await mountNav()

      await search(wrapper, '  ')

      expect(api.searchQuery).not.toHaveBeenCalled()
      expect(wrapper.get('[role="alert"]').text()).toContain('Enter a player name')
    })

    it('navigates straight to a single result', async () => {
      // Arrange
      api.searchQuery.mockResolvedValue([{ kind: 'player', id: 'p', steam_id: '765', label: 'Pleb' }])
      const { wrapper, router } = await mountNav()

      // Act
      await search(wrapper, 'pleb')

      // Assert
      expect(router.currentRoute.value.name).toBe('player-stats')
      expect(router.currentRoute.value.params.steamId).toBe('765')
    })

    it('lists several results and opens the chosen one', async () => {
      // Arrange
      api.searchQuery.mockResolvedValue([
        { kind: 'player', id: 'p1', steam_id: '1', label: 'One' },
        { kind: 'match', id: 'm1', match_id: 'm-1', label: 'Match one' },
      ])
      const { wrapper, router } = await mountNav()
      await search(wrapper, 'one')

      // Act
      const options = wrapper.findAll('#lookup-results button')
      await options[1].trigger('click')
      await flushPromises()

      // Assert
      expect(options).toHaveLength(2)
      expect(router.currentRoute.value.params.matchId).toBe('m-1')
    })

    it('falls back to a SteamID64 route when the API finds nothing', async () => {
      api.searchQuery.mockResolvedValue([])
      const { wrapper, router } = await mountNav()

      await search(wrapper, '[U:1:22202]')

      expect(router.currentRoute.value.name).toBe('player-stats')
      expect(router.currentRoute.value.params.steamId).toBe('76561197960287930')
    })

    it('treats a bare 17-digit SteamID64 as a player, not a logs.tf id', async () => {
      api.searchQuery.mockResolvedValue([])
      const { wrapper, router } = await mountNav()

      await search(wrapper, '76561197960287930')

      expect(router.currentRoute.value.name).toBe('player-stats')
    })

    it('treats a short number as a logs.tf id', async () => {
      api.searchQuery.mockResolvedValue([])
      const { wrapper, router } = await mountNav()

      await search(wrapper, '3209041')

      expect(router.currentRoute.value.name).toBe('match-stats')
      expect(router.currentRoute.value.params.matchId).toBe('3209041')
    })

    it('explains when nothing matches', async () => {
      api.searchQuery.mockResolvedValue([])
      const { wrapper } = await mountNav()

      await search(wrapper, 'nobody at all')

      expect(wrapper.get('[role="alert"]').text()).toBe('No match or player found for that query.')
    })
  })
})
