import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import EventView from './EventView.vue'
import { useEventQueryStore } from '../stores/eventQuery'

vi.mock('../api', () => ({
  fetchEvents: vi.fn(),
  fetchEventDetail: vi.fn(),
  fetchEventLeaderboard: vi.fn(),
}))

import * as api from '../api'

describe('EventView', () => {
  let router

  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/event/:eventId?', name: 'event', component: EventView, props: true },
        { path: '/player/:steamId?', name: 'player-stats', component: { template: '<div />' } },
      ],
    })
    api.fetchEvents.mockResolvedValue([
      { event_id: 'event-1', name: 'Season One', slug: 'season-one', tournament_count: 1, match_count: 2 },
    ])
    api.fetchEventDetail.mockResolvedValue({
      event: {
        event_id: 'event-1',
        name: 'Season One',
        slug: 'season-one',
        tournament_count: 1,
        match_count: 2,
      },
      tournaments: [{ tournament_id: 't-1', name: 'Invite', slug: 'invite', match_count: 2 }],
    })
    api.fetchEventLeaderboard.mockResolvedValue([
      {
        steam_id: 'STEAM_1:1:1',
        display_name: 'Scout',
        matches_played: 2,
        total_kills: 10,
        total_deaths: 4,
        total_assists: 3,
        average_damage_per_minute: 280,
        average_rating: 1.2,
        primary_class: 'scout',
      },
    ])
    await router.push('/event')
    await router.isReady()
  })

  it('renders the event list and leaderboard', async () => {
    const wrapper = mount(EventView, {
      props: { eventId: '' },
      global: { plugins: [router] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Season One')
    expect(wrapper.text()).toContain('Event leaderboard')
    expect(api.fetchEventLeaderboard).toHaveBeenCalled()

    const store = useEventQueryStore()
    expect(store.events).toHaveLength(1)
  })

  it('reloads leaderboard when class filter changes', async () => {
    const wrapper = mount(EventView, {
      props: { eventId: 'event-1' },
      global: { plugins: [router] },
    })
    await flushPromises()

    await wrapper.get('[data-test="class-scout"]').trigger('click')
    await flushPromises()

    expect(api.fetchEventLeaderboard).toHaveBeenCalledWith(
      'event-1',
      expect.objectContaining({ className: 'scout' }),
    )
  })

  it('deep-links child tournaments to the tournament dashboard', async () => {
    // Arrange
    const wrapper = mount(EventView, {
      props: { eventId: 'event-1' },
      global: { plugins: [router], stubs: { RouterLink: RouterLinkStub } },
    })
    await flushPromises()

    // Act
    const link = wrapper
      .findAllComponents(RouterLinkStub)
      .find((candidate) => candidate.text().startsWith('Invite'))

    // Assert
    expect(link.props('to')).toEqual({ name: 'tournament', query: { tournament: 't-1' } })
  })

  it('shows an empty state when no events exist', async () => {
    api.fetchEvents.mockResolvedValue([])

    const wrapper = mount(EventView, {
      props: { eventId: '' },
      global: { plugins: [router] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('No events yet.')
    expect(api.fetchEventDetail).not.toHaveBeenCalled()
  })

  it('shows an error when the event list fails to load', async () => {
    api.fetchEvents.mockRejectedValue(new Error('Network Error'))

    const wrapper = mount(EventView, {
      props: { eventId: '' },
      global: { plugins: [router] },
    })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('Network Error')
  })
})
