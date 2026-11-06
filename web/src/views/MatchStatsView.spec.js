import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { RouterLink } from 'vue-router'
import { createTestingPinia } from '@pinia/testing'
import MatchStatsView from './MatchStatsView.vue'
import { createTestRouter } from '../test/helpers'
import * as api from '../api'

vi.mock('../api', () => ({
  fetchMatches: vi.fn(),
  fetchMatchDetail: vi.fn(),
  fetchTournaments: vi.fn(),
}))

const MATCH_ID = '11111111-2222-3333-4444-555555555555'

const DETAIL = {
  match_summary: {
    match_id: MATCH_ID,
    map_name: 'cp_process_final',
    winning_team: 'blu',
    blu_score: 5,
    red_score: 3,
    duration_seconds: 1800,
    date_played: '2024-05-01T12:00:00Z',
    ratings_ready: true,
  },
  players: [
    { steam_id: 's-blu', display_name: 'Blu Scout', team: 'blu', rating: 1.2, kills: 20, deaths: 5, assists: 3 },
    { steam_id: 's-red', display_name: 'Red Demo', team: 'red', rating: 0.9, kills: 10, deaths: 9, assists: 4 },
  ],
}

async function mountView(path = '/match') {
  const router = createTestRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(MatchStatsView, {
    global: {
      plugins: [router, createTestingPinia({ createSpy: vi.fn, stubActions: false })],
      // Real links so row clicks navigate.
      stubs: { RouterLink },
    },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('MatchStatsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchMatches.mockResolvedValue([
      {
      match_id: MATCH_ID,
      tournament_id: 't-1',
      map_name: 'cp_process_final',
      winning_team: 'blu',
      blu_score: 4,
      red_score: 1,
      date_played: '2024-05-01T12:00:00Z',
    },
    ])
    api.fetchMatchDetail.mockResolvedValue(DETAIL)
    api.fetchTournaments.mockResolvedValue([{ tournament_id: 't-1', name: 'Invite' }])
  })

  describe('without a match id (/match)', () => {
    it('shows the results list grouped by day, with tournament names', async () => {
      const { wrapper } = await mountView('/match')

      expect(api.fetchMatchDetail).not.toHaveBeenCalled()
      expect(wrapper.get('h1').text()).toBe('Results')
      const rows = wrapper.findAll('[data-test="result-row"]')
      expect(rows).toHaveLength(1)
      expect(rows[0].text()).toContain('4')
      expect(rows[0].text()).toContain('cp_process_final')
      expect(rows[0].text()).toContain('Invite')
      expect(wrapper.find('[data-test="result-list"] h3').text()).toContain('2024')
    })

    it('opens a match when its row is activated', async () => {
      // Arrange
      const { wrapper, router } = await mountView('/match')

      // Act
      await wrapper.get('[data-test="result-row"]').trigger('click')
      await flushPromises()

      // Assert
      expect(router.currentRoute.value.params.matchId).toBe(MATCH_ID)
    })
  })

  describe('with a match id', () => {
    it('renders the scorebox and one scoreboard per team, without the results list', async () => {
      const { wrapper } = await mountView(`/match/${MATCH_ID}`)

      expect(api.fetchMatchDetail).toHaveBeenCalledWith(MATCH_ID)
      expect(api.fetchMatches).not.toHaveBeenCalled()
      expect(wrapper.find('[data-test="scorebox"]').exists()).toBe(true)
      expect(wrapper.get('[data-test="scoreboard-blu"]').text()).toContain('Blu Scout')
      expect(wrapper.get('[data-test="scoreboard-red"]').text()).toContain('Red Demo')
      expect(wrapper.find('[data-test="result-list"]').exists()).toBe(false)
    })

    it('shows the tournament name in the scorebox', async () => {
      api.fetchMatchDetail.mockResolvedValue({
        ...DETAIL,
        match_summary: { ...DETAIL.match_summary, tournament_id: 't-1' },
      })

      const { wrapper } = await mountView(`/match/${MATCH_ID}`)

      expect(wrapper.get('[data-test="scorebox"]').text()).toContain('Invite')
    })

    it('hides niche stat columns nobody recorded, and shows them when someone did', async () => {
      // Arrange
      const withUbers = {
        ...DETAIL,
        players: [{ ...DETAIL.players[0], ubers: 3 }, DETAIL.players[1]],
      }

      // Act
      const quiet = (await mountView(`/match/${MATCH_ID}`)).wrapper
      api.fetchMatchDetail.mockResolvedValue(withUbers)
      const busy = (await mountView(`/match/${MATCH_ID}`)).wrapper

      // Assert
      const headers = (w) => w.get('[data-test="scoreboard-blu"]').findAll('th').map((th) => th.text())
      expect(headers(quiet)).not.toContain('Ubers')
      expect(headers(busy)).toContain('Ubers')
    })

    it('links back to all results', async () => {
      const { wrapper } = await mountView(`/match/${MATCH_ID}`)

      expect(wrapper.text()).toContain('All results')
    })

    it('shows a skeleton while the detail loads', async () => {
      api.fetchMatchDetail.mockReturnValue(new Promise(() => {}))

      const { wrapper } = await mountView(`/match/${MATCH_ID}`)

      expect(wrapper.find('[aria-label="Loading match details"]').exists()).toBe(true)
    })

    it('shows an error when the detail request fails', async () => {
      api.fetchMatchDetail.mockRejectedValue(new Error('404 Not Found'))

      const { wrapper } = await mountView(`/match/${MATCH_ID}`)

      expect(wrapper.get('[role="alert"]').text()).toBe('404 Not Found')
      expect(wrapper.text()).not.toContain('Team breakdown')
    })

    it('shows an empty message when the match has no player rows', async () => {
      api.fetchMatchDetail.mockResolvedValue({ ...DETAIL, players: [] })

      const { wrapper } = await mountView(`/match/${MATCH_ID}`)

      expect(wrapper.text()).toContain('No player rows for this match yet.')
    })
  })

  describe('match list', () => {
    it('shows an empty message when nothing is projected', async () => {
      api.fetchMatches.mockResolvedValue([])

      const { wrapper } = await mountView('/match')

      expect(wrapper.text()).toContain('No matches found.')
    })

    it('shows list errors', async () => {
      api.fetchMatches.mockRejectedValue(new Error('Network Error'))

      const { wrapper } = await mountView('/match')

      expect(wrapper.get('[role="alert"]').text()).toBe('Network Error')
    })
  })
})
