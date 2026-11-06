import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import TournamentView from './TournamentView.vue'
import { createTestRouter } from '../test/helpers'
import * as api from '../api'

vi.mock('../api', () => ({
  fetchAuthMe: vi.fn(),
  getSteamLoginUrl: vi.fn(() => '/login'),
  getQueryBaseUrl: vi.fn(() => '/api/query'),
  fetchEvents: vi.fn(),
  fetchTournaments: vi.fn(),
  fetchMatches: vi.fn(),
  fetchTournamentLeaderboard: vi.fn(),
  fetchClassBenchmarks: vi.fn(),
}))

const INVITE = { tournament_id: 't-1', name: 'Invite', slug: 'invite', match_count: 2, event_id: 'e-1' }
const OPEN = { tournament_id: 't-2', name: 'Open', slug: 'open', match_count: 1, event_id: null }

async function mountView({ path = '/', auth = { token: '', user: null } } = {}) {
  const router = createTestRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(TournamentView, {
    global: {
      plugins: [
        router,
        createTestingPinia({ createSpy: vi.fn, stubActions: false, initialState: { auth } }),
      ],
    },
  })
  await flushPromises()
  return wrapper
}

describe('TournamentView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchEvents.mockResolvedValue([{ event_id: 'e-1', name: 'Season One' }])
    api.fetchTournaments.mockResolvedValue([INVITE, OPEN])
    api.fetchMatches.mockResolvedValue([
      { match_id: 'abcdef12-0000', map_name: 'cp_gully', winning_team: 'red', duration_seconds: 1500 },
    ])
    api.fetchTournamentLeaderboard.mockResolvedValue([
      { steam_id: 's-1', display_name: 'Scout Main', average_rating: 1.3, total_kills: 5, total_deaths: 1, total_assists: 2 },
    ])
    api.fetchClassBenchmarks.mockResolvedValue([{ class_name: 'scout', sample_size: 4, avg_rating: 1 }])
  })

  describe('populated', () => {
    it('selects the first tournament and loads its matches and leaderboard', async () => {
      // Arrange / Act
      const wrapper = await mountView()

      // Assert
      expect(api.fetchMatches).toHaveBeenCalledWith(expect.objectContaining({ tournamentId: 't-1' }))
      expect(api.fetchTournamentLeaderboard).toHaveBeenCalledWith('t-1', expect.anything())
      expect(wrapper.text()).toContain('cp_gully')
      expect(wrapper.text()).toContain('Scout Main')
      expect(wrapper.text()).toContain('25m')
    })

    it('honours a ?tournament= deep link from the event page', async () => {
      await mountView({ path: '/?tournament=t-2' })

      expect(api.fetchTournamentLeaderboard).toHaveBeenCalledWith('t-2', expect.anything())
      expect(api.fetchTournamentLeaderboard).not.toHaveBeenCalledWith('t-1', expect.anything())
    })

    it('ignores an unknown ?tournament= id', async () => {
      await mountView({ path: '/?tournament=missing' })

      expect(api.fetchTournamentLeaderboard).toHaveBeenCalledWith('t-1', expect.anything())
    })

    it('reloads the leaderboard when the class filter changes', async () => {
      // Arrange
      const wrapper = await mountView()
      api.fetchTournamentLeaderboard.mockClear()

      // Act
      await wrapper.get('[data-test="class-medic"]').trigger('click')
      await flushPromises()

      // Assert
      expect(api.fetchTournamentLeaderboard).toHaveBeenCalledWith(
        't-1',
        expect.objectContaining({ className: 'medic' }),
      )
      expect(wrapper.get('[data-test="class-medic"]').attributes('aria-pressed')).toBe('true')
    })

    it('switches tournaments from the tab row', async () => {
      // Arrange
      const wrapper = await mountView()
      api.fetchTournamentLeaderboard.mockClear()
      const openTab = wrapper
        .findAll('[data-test="tournament-tabs"] button')
        .find((tab) => tab.text().startsWith('Open'))

      // Act
      await openTab.trigger('click')
      await flushPromises()

      // Assert
      expect(openTab.attributes('aria-pressed')).toBe('true')
      expect(api.fetchTournamentLeaderboard).toHaveBeenCalledWith('t-2', expect.anything())
      expect(api.fetchMatches).toHaveBeenLastCalledWith(expect.objectContaining({ tournamentId: 't-2' }))
    })

    it('loads each dataset once on first render', async () => {
      await mountView()

      expect(api.fetchTournamentLeaderboard).toHaveBeenCalledTimes(1)
      expect(api.fetchMatches).toHaveBeenCalledTimes(1)
      expect(api.fetchClassBenchmarks).toHaveBeenCalledTimes(1)
    })
  })

  describe('loading', () => {
    it('shows only the skeleton (no duplicate loading text)', async () => {
      // Arrange
      api.fetchTournaments.mockReturnValue(new Promise(() => {}))

      // Act
      const wrapper = await mountView()

      // Assert
      expect(wrapper.find('[aria-label="Loading tournaments"]').exists()).toBe(true)
      expect(wrapper.text()).not.toMatch(/Loading tournament index/)
    })
  })

  describe('empty', () => {
    it('shows an empty state, not an error, when there are no tournaments', async () => {
      api.fetchTournaments.mockResolvedValue([])

      const wrapper = await mountView()

      expect(wrapper.text()).toContain('No tournaments projected yet.')
      expect(wrapper.text()).toContain('Check back once an admin has ingested logs.')
      expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    })

    it('points admins to the tournament admin page', async () => {
      api.fetchTournaments.mockResolvedValue([])

      const wrapper = await mountView({ auth: { token: 'tok', user: { role: 'ADMIN', steam_id: '1' } } })

      expect(wrapper.text()).toContain('Create one in Admin')
    })
  })

  describe('errors', () => {
    it('shows the tournament load error', async () => {
      api.fetchTournaments.mockRejectedValue(new Error('502 Bad Gateway'))

      const wrapper = await mountView()

      expect(wrapper.get('[role="alert"]').text()).toBe('502 Bad Gateway')
    })

    it('shows leaderboard errors inside the leaderboard panel', async () => {
      api.fetchTournamentLeaderboard.mockRejectedValue(new Error('timeout'))

      const wrapper = await mountView()

      expect(wrapper.get('[role="alert"]').text()).toBe('timeout')
      expect(wrapper.text()).toContain('cp_gully')
    })
  })
})
