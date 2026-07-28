import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PlayerStatsTable from './PlayerStatsTable.vue'

describe('PlayerStatsTable', () => {
  it('shows display name with steam id fallback and rating chip', () => {
    const wrapper = mount(PlayerStatsTable, {
      props: {
        stats: {
          steam_id: 'STEAM_1:1:12345',
          display_name: 'Tomahawk',
          matches_played: 3,
          total_kills: 30,
          total_deaths: 12,
          total_assists: 9,
          average_damage_per_minute: 320.5,
          total_healing_done: 0,
          average_rating: 1.25,
          class_breakdown: [
            {
              class_name: 'scout',
              matches_played: 3,
              total_kills: 30,
              total_deaths: 12,
              total_assists: 9,
              average_damage_per_minute: 320.5,
              total_healing_done: 0,
              average_rating: 1.25,
            },
          ],
        },
        formatNumber: (value, digits = 2) => Number(value).toFixed(digits),
      },
    })

    expect(wrapper.text()).toContain('Tomahawk')
    expect(wrapper.text()).toContain('STEAM_1:1:12345')
    expect(wrapper.text()).toContain('scout')
    expect(wrapper.find('.rating-chip').exists()).toBe(true)
  })

  it('falls back to steam id when display name is missing', () => {
    const wrapper = mount(PlayerStatsTable, {
      props: {
        stats: {
          steam_id: 'STEAM_1:1:99999',
          display_name: null,
          matches_played: 1,
          total_kills: 1,
          total_deaths: 1,
          total_assists: 0,
          average_damage_per_minute: 100,
          total_healing_done: 0,
          average_rating: 1.0,
          class_breakdown: [],
        },
        formatNumber: (value) => String(value),
      },
    })

    expect(wrapper.text()).toContain('STEAM_1:1:99999')
  })
})
