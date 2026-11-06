import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AdminMatchesView from './AdminMatchesView.vue'
import { createTestRouter } from '../../test/helpers'
import * as api from '../../api'

vi.mock('../../api', () => ({
  assignMatchTournament: vi.fn(),
  fetchMatches: vi.fn(),
  fetchTournaments: vi.fn(),
}))

vi.mock('../../utils/poll', () => ({
  pollUntil: vi.fn(async (predicate) => predicate()),
}))

const MATCH = { match_id: 'aaaaaaaa-1111', map_name: 'cp_process_final', tournament_id: '' }
const TOURNAMENTS = [{ tournament_id: 't-1', name: 'Invite' }]

async function mountView() {
  const wrapper = mount(AdminMatchesView, {
    global: { plugins: [createTestRouter(), createTestingPinia({ createSpy: vi.fn })] },
  })
  await flushPromises()
  return wrapper
}

const saveButton = (wrapper) => wrapper.findAll('tbody button').find((b) => b.text() === 'Save')

describe('AdminMatchesView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchMatches.mockResolvedValue([MATCH])
    api.fetchTournaments.mockResolvedValue(TOURNAMENTS)
  })

  it('lists projected matches with a tournament picker per row', async () => {
    const wrapper = await mountView()

    expect(api.fetchMatches).toHaveBeenCalledWith({ skip: 0, limit: 50 })
    expect(wrapper.text()).toContain('cp_process_final')
    expect(wrapper.find('select[aria-label="Tournament for match aaaaaaaa"]').exists()).toBe(true)
  })

  it('shows an empty message when no matches are projected', async () => {
    api.fetchMatches.mockResolvedValue([])

    const wrapper = await mountView()

    expect(wrapper.text()).toContain('No matches projected yet.')
  })

  it('surfaces load failures', async () => {
    api.fetchMatches.mockRejectedValue(new Error('timeout'))

    const wrapper = await mountView()

    expect(wrapper.get('[role="alert"]').text()).toBe('timeout')
  })

  it('refuses to save without a tournament selected', async () => {
    // Arrange
    const wrapper = await mountView()

    // Act
    await saveButton(wrapper).trigger('click')

    // Assert
    expect(api.assignMatchTournament).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Select a tournament before saving.')
  })

  it('assigns the match and confirms with the tournament name', async () => {
    // Arrange
    api.assignMatchTournament.mockResolvedValue({})
    api.fetchMatches.mockResolvedValueOnce([MATCH]).mockResolvedValue([{ ...MATCH, tournament_id: 't-1' }])
    const wrapper = await mountView()

    // Act
    await wrapper.get('tbody select').setValue('t-1')
    await saveButton(wrapper).trigger('click')
    await flushPromises()

    // Assert
    expect(api.assignMatchTournament).toHaveBeenCalledWith('aaaaaaaa-1111', { tournament_id: 't-1' })
    expect(wrapper.text()).toContain('Assigned match to Invite')
  })

  it('reports assignment failures', async () => {
    api.assignMatchTournament.mockRejectedValue(new Error('403 Forbidden'))
    const wrapper = await mountView()

    await wrapper.get('tbody select').setValue('t-1')
    await saveButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('403 Forbidden')
  })
})
