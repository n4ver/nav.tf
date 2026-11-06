import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import PlayerStatsView from './PlayerStatsView.vue'
import { createTestRouter } from '../test/helpers'
import * as api from '../api'

vi.mock('../api', () => ({
  fetchPlayerStats: vi.fn(),
}))

const STEAM64 = '76561197960287930'

const STATS = {
  steam_id: STEAM64,
  display_name: 'Tomahawk',
  matches_played: 2,
  total_kills: 30,
  total_deaths: 10,
  total_assists: 8,
  average_damage_per_minute: 310.2,
  total_healing_done: 0,
  average_rating: 1.1,
  class_breakdown: [],
  recent_matches: [
    {
      match_id: 'm-1',
      date_played: '2024-05-01T12:00:00Z',
      map_name: 'cp_gully',
      team: 'blu',
      classes_played: ['scout'],
      kills: 15,
      deaths: 5,
      assists: 4,
      damage_per_minute: 300,
      rating: 1.2,
    },
  ],
}

async function mountView(path = '/player') {
  const router = createTestRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(PlayerStatsView, {
    global: {
      plugins: [router, createTestingPinia({ createSpy: vi.fn, stubActions: false })],
    },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('PlayerStatsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchPlayerStats.mockResolvedValue(STATS)
  })

  describe('without a steam id (/player)', () => {
    it('shows a search landing instead of a blank panel', async () => {
      const { wrapper } = await mountView('/player')

      expect(api.fetchPlayerStats).not.toHaveBeenCalled()
      expect(wrapper.text()).toContain('Enter a SteamID above')
    })

    it('navigates to the SteamID64 route on lookup and loads once', async () => {
      // Arrange
      const { wrapper, router } = await mountView('/player')

      // Act
      await wrapper.get('input').setValue('[U:1:22202]')
      await wrapper.get('form').trigger('submit.prevent')
      await flushPromises()

      // Assert
      expect(router.currentRoute.value.params.steamId).toBe(STEAM64)
      expect(api.fetchPlayerStats).toHaveBeenCalledTimes(1)
      expect(api.fetchPlayerStats).toHaveBeenCalledWith(STEAM64)
    })
  })

  describe('with a steam id', () => {
    it('renders the career summary and recent matches', async () => {
      const { wrapper } = await mountView(`/player/${STEAM64}`)

      expect(wrapper.text()).toContain('Tomahawk')
      expect(wrapper.text()).toContain('Recent matches')
      expect(wrapper.text()).toContain('cp_gully')
      expect(wrapper.get('a[href^="https://steamcommunity.com/profiles/"]').attributes('href')).toContain(STEAM64)
    })

    it('force-refreshes when looking up the already-open player', async () => {
      // Arrange
      const { wrapper } = await mountView(`/player/${STEAM64}`)
      api.fetchPlayerStats.mockClear()

      // Act
      await wrapper.get('form').trigger('submit.prevent')
      await flushPromises()

      // Assert
      expect(api.fetchPlayerStats).toHaveBeenCalledTimes(1)
    })

    it('shows a skeleton while loading', async () => {
      api.fetchPlayerStats.mockReturnValue(new Promise(() => {}))

      const { wrapper } = await mountView(`/player/${STEAM64}`)

      expect(wrapper.find('[aria-label="Loading player stats"]').exists()).toBe(true)
    })

    it('shows the error and no stale stats when the request fails', async () => {
      api.fetchPlayerStats.mockRejectedValue(new Error('404 Not Found'))

      const { wrapper } = await mountView(`/player/${STEAM64}`)

      expect(wrapper.get('[role="alert"]').text()).toBe('404 Not Found')
      expect(wrapper.text()).not.toContain('Recent matches')
    })

    it('explains when the player has no projected matches', async () => {
      api.fetchPlayerStats.mockResolvedValue({ ...STATS, matches_played: 0, recent_matches: [] })

      const { wrapper } = await mountView(`/player/${STEAM64}`)

      expect(wrapper.text()).toContain('No projected stats yet for this SteamID.')
      expect(wrapper.text()).not.toContain('Recent matches')
    })
  })
})
