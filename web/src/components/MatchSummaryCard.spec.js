import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MatchSummaryCard from './MatchSummaryCard.vue'

describe('MatchSummaryCard', () => {
  it('renders map, winner, duration, and date', () => {
    const wrapper = mount(MatchSummaryCard, {
      props: {
        summary: {
          map_name: 'cp_process_final',
          winning_team: 'blu',
          duration_seconds: 1500,
          date_played: '2026-07-01T12:00:00Z',
        },
        formatDuration: (seconds) => `${Math.floor(seconds / 60)}m`,
        formatDate: (value) => String(value).slice(0, 10),
      },
    })

    expect(wrapper.text()).toContain('cp_process_final')
    expect(wrapper.text()).toContain('blu')
    expect(wrapper.text()).toContain('25m')
    expect(wrapper.text()).toContain('2026-07-01')
  })
})
