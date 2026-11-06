import { describe, expect, it } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import MatchResultList from './MatchResultList.vue'

const ROWS = [
  {
    match_id: 'old',
    tournament_id: 't-1',
    map_name: 'cp_gully',
    winning_team: 'red',
    blu_score: 1,
    red_score: 4,
    duration_seconds: 1200,
    date_played: '2024-05-01T12:00:00Z',
  },
  {
    match_id: 'new',
    tournament_id: 't-1',
    map_name: 'koth_product',
    winning_team: 'blu',
    blu_score: 3,
    red_score: 0,
    duration_seconds: 900,
    date_played: '2024-05-02T12:00:00Z',
  },
]

function mountList(props) {
  return mount(MatchResultList, {
    props,
    global: { stubs: { RouterLink: RouterLinkStub } },
  })
}

describe('MatchResultList', () => {
  it('lists newest first with each row linking to its match', () => {
    // Arrange / Act
    const wrapper = mountList({ matches: ROWS })

    // Assert
    const links = wrapper.findAllComponents(RouterLinkStub)
    expect(links.map((link) => link.props('to'))).toEqual(['/match/new', '/match/old'])
  })

  it('colours the winning score green and the losing score red', () => {
    const wrapper = mountList({ matches: [ROWS[0]] })

    const scores = wrapper.findAll('[data-test="result-row"] .tabular-nums span')
    const blu = scores.find((span) => span.text() === '1')
    const red = scores.find((span) => span.text() === '4')
    expect(blu.classes()).toContain('text-danger')
    expect(red.classes()).toContain('text-ok')
  })

  it('adds one day header per date when grouped', () => {
    const wrapper = mountList({ matches: ROWS, groupByDay: true })

    expect(wrapper.findAll('h3')).toHaveLength(2)
  })

  it('shows tournament names on full rows when provided', () => {
    const wrapper = mountList({ matches: ROWS, tournamentNames: { 't-1': 'Invite' } })

    expect(wrapper.get('[data-test="result-row"]').text()).toContain('Invite')
  })

  it('renders the compact sidebar variant with map and duration', () => {
    const wrapper = mountList({ matches: [ROWS[1]], compact: true })

    const row = wrapper.get('[data-test="result-row"]')
    expect(row.text()).toContain('koth_product')
    expect(row.text()).toContain('15m')
  })

  it('shows a skeleton while loading and a message when empty', () => {
    expect(mountList({ matches: [], loading: true }).find('[aria-busy="true"]').exists()).toBe(true)
    expect(mountList({ matches: [], emptyMessage: 'Nothing yet' }).text()).toContain('Nothing yet')
  })
})
