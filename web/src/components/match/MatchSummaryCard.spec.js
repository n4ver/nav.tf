import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MatchSummaryCard from './MatchSummaryCard.vue'

const SUMMARY = {
  match_id: '11111111-1111-1111-1111-111111111111',
  map_name: 'cp_process_final',
  winning_team: 'blu',
  blu_score: 2,
  red_score: 1,
  duration_seconds: 1500,
  date_played: '2026-07-01T12:00:00Z',
  source_log_id: 3209041,
  ratings_ready: true,
}

describe('MatchSummaryCard', () => {
  it('renders both sides, the score and match metadata', () => {
    // Arrange / Act
    const wrapper = mount(MatchSummaryCard, { props: { summary: SUMMARY, tournamentName: 'Invite' } })

    // Assert
    expect(wrapper.text()).toContain('BLU')
    expect(wrapper.text()).toContain('RED')
    expect(wrapper.get('[data-test="blu-score"]').text()).toBe('2')
    expect(wrapper.get('[data-test="red-score"]').text()).toBe('1')
    expect(wrapper.text()).toContain('cp_process_final')
    expect(wrapper.text()).toContain('25m 00s')
    expect(wrapper.text()).toContain('Invite')
  })

  it('colours the winning score green and the losing score red', () => {
    const wrapper = mount(MatchSummaryCard, { props: { summary: SUMMARY } })

    expect(wrapper.get('[data-test="blu-score"]').classes()).toContain('text-ok')
    expect(wrapper.get('[data-test="red-score"]').classes()).toContain('text-danger')
    expect(wrapper.text()).toContain('BLU won')
  })

  it('links to the source log on logs.tf', () => {
    const wrapper = mount(MatchSummaryCard, { props: { summary: SUMMARY } })

    expect(wrapper.get('a').attributes('href')).toBe('https://logs.tf/3209041')
  })

  it('omits the logs.tf link for uploaded logs and flags pending ratings', () => {
    const wrapper = mount(MatchSummaryCard, {
      props: { summary: { ...SUMMARY, source_log_id: null, ratings_ready: false } },
    })

    expect(wrapper.find('a').exists()).toBe(false)
    expect(wrapper.text()).toContain('Ratings pending')
  })
})
