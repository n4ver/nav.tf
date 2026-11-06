import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PlayerLeaderboard from './PlayerLeaderboard.vue'

const ROWS = [
  { steam_id: 'a', display_name: 'Ace', primary_class: 'scout', total_kills: 30, total_deaths: 10, average_rating: 1.3 },
  { steam_id: 'b', display_name: 'Bee', primary_class: 'medic', total_kills: 2, total_deaths: 20, average_rating: 0.8 },
]

describe('PlayerLeaderboard', () => {
  it('ranks rows in API order and shows +/- with sign and colour', () => {
    // Arrange / Act
    const wrapper = mount(PlayerLeaderboard, { props: { rows: ROWS } })

    // Assert
    const bodyRows = wrapper.findAll('tbody tr')
    expect(bodyRows[0].text()).toContain('1')
    expect(bodyRows[0].text()).toContain('Ace')
    expect(bodyRows[0].text()).toContain('+20')
    expect(bodyRows[1].text()).toContain('-18')
    expect(bodyRows[1].find('.text-danger').exists()).toBe(true)
  })

  it('emits the chosen class and marks it pressed', async () => {
    // Arrange
    const wrapper = mount(PlayerLeaderboard, { props: { rows: ROWS, classFilter: '' } })

    // Act
    await wrapper.get('[data-test="class-medic"]').trigger('click')

    // Assert
    expect(wrapper.emitted('update:classFilter')).toEqual([['medic']])
    await wrapper.setProps({ classFilter: 'medic' })
    expect(wrapper.get('[data-test="class-medic"]').attributes('aria-pressed')).toBe('true')
  })

  it('shows errors instead of the table', () => {
    const wrapper = mount(PlayerLeaderboard, { props: { rows: ROWS, error: 'boom' } })

    expect(wrapper.get('[role="alert"]').text()).toBe('boom')
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('hides secondary columns on phones', () => {
    const wrapper = mount(PlayerLeaderboard, { props: { rows: ROWS } })

    const classHeader = wrapper.findAll('th').find((th) => th.text().startsWith('Class'))
    expect(classHeader.classes()).toEqual(expect.arrayContaining(['hidden', 'md:table-cell']))
  })
})
