import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PlayerCareerSummary from './PlayerCareerSummary.vue'

const STATS = {
  steam_id: '76561197960287930',
  display_name: 'Tomahawk',
  matches_played: 3,
  total_kills: 30,
  total_deaths: 12,
  total_assists: 9,
  average_damage_per_minute: 320.5,
  total_healing_done: 0,
  average_rating: 1.25,
}

describe('PlayerCareerSummary', () => {
  it('shows identity, Steam link and the headline rating', () => {
    // Arrange / Act
    const wrapper = mount(PlayerCareerSummary, { props: { stats: STATS } })

    // Assert
    expect(wrapper.get('h1').text()).toBe('Tomahawk')
    expect(wrapper.text()).toContain(STATS.steam_id)
    expect(wrapper.get('a').attributes('href')).toBe(
      'https://steamcommunity.com/profiles/76561197960287930',
    )
    const rating = wrapper.get('.rating-chip')
    expect(rating.text()).toBe('1.25')
    expect(rating.classes()).toContain('tone-high')
  })

  it('derives K/D ratio and formats DPM in the stat strip', () => {
    const wrapper = mount(PlayerCareerSummary, { props: { stats: STATS } })

    expect(wrapper.text()).toContain('K/D ratio')
    expect(wrapper.text()).toContain('2.50')
    expect(wrapper.text()).toContain('320.5')
  })

  it('falls back to the steam id when the display name is missing', () => {
    const wrapper = mount(PlayerCareerSummary, {
      props: { stats: { ...STATS, display_name: null, total_deaths: 0 } },
    })

    expect(wrapper.get('h1').text()).toBe(STATS.steam_id)
    expect(wrapper.text()).toContain('∞')
  })
})
