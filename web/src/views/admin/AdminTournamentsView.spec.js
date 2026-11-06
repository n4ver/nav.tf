import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AdminTournamentsView from './AdminTournamentsView.vue'
import { createTestRouter } from '../../test/helpers'
import * as api from '../../api'

vi.mock('../../api', () => ({
  createTournament: vi.fn(),
  fetchEvents: vi.fn(),
  fetchTournaments: vi.fn(),
  linkTournamentToEvent: vi.fn(),
  updateTournament: vi.fn(),
}))

// Run the predicate once instead of waiting on real timers.
vi.mock('../../utils/poll', () => ({
  pollUntil: vi.fn(async (predicate) => predicate()),
}))

const EVENTS = [{ event_id: 'e-1', name: 'Season One' }]
const INVITE = { tournament_id: 't-1', name: 'Invite', slug: 'invite', match_count: 4, event_id: null }

async function mountView() {
  const router = createTestRouter()
  const wrapper = mount(AdminTournamentsView, {
    global: { plugins: [router, createTestingPinia({ createSpy: vi.fn })] },
  })
  await flushPromises()
  return wrapper
}

describe('AdminTournamentsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchEvents.mockResolvedValue(EVENTS)
    api.fetchTournaments.mockResolvedValue([INVITE])
  })

  describe('loading and empty states', () => {
    it('shows a skeleton while loading', async () => {
      // Arrange: never-resolving request keeps the view in its loading state
      api.fetchTournaments.mockReturnValue(new Promise(() => {}))

      // Act
      const wrapper = mount(AdminTournamentsView, {
        global: { plugins: [createTestRouter(), createTestingPinia({ createSpy: vi.fn })] },
      })
      await wrapper.vm.$nextTick()

      // Assert
      expect(wrapper.find('[aria-busy="true"]').exists()).toBe(true)
    })

    it('shows an empty message when no tournaments exist', async () => {
      api.fetchTournaments.mockResolvedValue([])

      const wrapper = await mountView()

      expect(wrapper.text()).toContain('No tournaments yet.')
    })

    it('surfaces load errors', async () => {
      api.fetchTournaments.mockRejectedValue(new Error('boom'))

      const wrapper = await mountView()

      expect(wrapper.get('[role="alert"]').text()).toBe('boom')
    })
  })

  describe('create', () => {
    it('submits name, slug and optional event, then confirms', async () => {
      // Arrange
      api.createTournament.mockResolvedValue({ tournament_id: 't-2', name: 'Open' })
      api.fetchTournaments
        .mockResolvedValueOnce([INVITE])
        .mockResolvedValue([INVITE, { ...INVITE, tournament_id: 't-2', name: 'Open', slug: 'open' }])
      const wrapper = await mountView()
      const form = wrapper.get('form')

      // Act
      await form.get('input[placeholder="Invite Bracket"]').setValue(' Open ')
      await form.get('input[placeholder="invite-bracket"]').setValue('open')
      await form.get('select').setValue('e-1')
      await form.trigger('submit.prevent')
      await flushPromises()

      // Assert
      expect(api.createTournament).toHaveBeenCalledWith({ name: 'Open', slug: 'open', event_id: 'e-1' })
      expect(wrapper.text()).toContain('Created tournament Open')
    })

    it('shows the API error when create fails', async () => {
      api.createTournament.mockRejectedValue(new Error('409 Conflict'))
      const wrapper = await mountView()

      await wrapper.get('form').trigger('submit.prevent')
      await flushPromises()

      expect(wrapper.get('[role="alert"]').text()).toBe('409 Conflict')
    })
  })

  describe('edit', () => {
    it('saves the edited name and slug', async () => {
      // Arrange
      api.updateTournament.mockResolvedValue({ tournament_id: 't-1', name: 'Invite Plus' })
      api.fetchTournaments
        .mockResolvedValueOnce([INVITE])
        .mockResolvedValue([{ ...INVITE, name: 'Invite Plus' }])
      const wrapper = await mountView()

      // Act
      await wrapper.findAll('button').find((button) => button.text() === 'Edit').trigger('click')
      await wrapper.get('input[aria-label="Tournament name"]').setValue('Invite Plus')
      await wrapper.findAll('button').find((button) => button.text() === 'Save').trigger('click')
      await flushPromises()

      // Assert
      expect(api.updateTournament).toHaveBeenCalledWith('t-1', { name: 'Invite Plus', slug: 'invite' })
      expect(wrapper.text()).toContain('Updated tournament Invite Plus')
    })
  })

  describe('event link', () => {
    it('links a tournament to an event from the row select', async () => {
      // Arrange
      api.linkTournamentToEvent.mockResolvedValue({})
      api.fetchTournaments.mockResolvedValueOnce([INVITE]).mockResolvedValue([{ ...INVITE, event_id: 'e-1' }])
      const wrapper = await mountView()

      // Act
      await wrapper.get('select[aria-label="Event for Invite"]').setValue('e-1')
      await flushPromises()

      // Assert
      expect(api.linkTournamentToEvent).toHaveBeenCalledWith('t-1', { event_id: 'e-1' })
      expect(wrapper.text()).toContain('Linked tournament to event')
    })
  })
})
