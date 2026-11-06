import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AdminPlayersView from './AdminPlayersView.vue'
import * as api from '../../api'

vi.mock('../../api', () => ({
  searchQuery: vi.fn(),
  updatePlayerDisplayName: vi.fn(),
}))

const PLAYER = { kind: 'player', steam_id: '76561197960287930', display_name: 'Old', label: 'Old' }

function mountView() {
  return mount(AdminPlayersView, {
    global: { plugins: [createTestingPinia({ createSpy: vi.fn })] },
  })
}

async function search(wrapper, query) {
  await wrapper.get('form input').setValue(query)
  await wrapper.get('form').trigger('submit.prevent')
  await flushPromises()
}

describe('AdminPlayersView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('search', () => {
    it('requires a query', async () => {
      const wrapper = mountView()

      await search(wrapper, '   ')

      expect(api.searchQuery).not.toHaveBeenCalled()
      expect(wrapper.get('[role="alert"]').text()).toContain('Enter a SteamID')
    })

    it('keeps only player results', async () => {
      // Arrange
      api.searchQuery.mockResolvedValue([PLAYER, { kind: 'match', match_id: 'm-1', label: 'Match' }])
      const wrapper = mountView()

      // Act
      await search(wrapper, 'old')

      // Assert
      expect(api.searchQuery).toHaveBeenCalledWith('old', { limit: 20 })
      expect(wrapper.findAll('tbody tr')).toHaveLength(1)
      expect(wrapper.text()).toContain(PLAYER.steam_id)
    })

    it('reports when no players match', async () => {
      api.searchQuery.mockResolvedValue([{ kind: 'match', match_id: 'm-1' }])
      const wrapper = mountView()

      await search(wrapper, 'nobody')

      expect(wrapper.get('[role="alert"]').text()).toBe('No players found.')
    })

    it('reports search failures', async () => {
      api.searchQuery.mockRejectedValue(new Error('500 Internal Server Error'))
      const wrapper = mountView()

      await search(wrapper, 'x')

      expect(wrapper.get('[role="alert"]').text()).toBe('500 Internal Server Error')
    })
  })

  describe('alias update', () => {
    it('rejects an empty alias', async () => {
      // Arrange
      api.searchQuery.mockResolvedValue([{ ...PLAYER }])
      const wrapper = mountView()
      await search(wrapper, 'old')

      // Act
      await wrapper.get('tbody button').trigger('click')

      // Assert
      expect(api.updatePlayerDisplayName).not.toHaveBeenCalled()
      expect(wrapper.text()).toContain('Display name cannot be empty.')
    })

    it('saves a new alias and updates the row', async () => {
      // Arrange
      api.searchQuery.mockResolvedValue([{ ...PLAYER }])
      api.updatePlayerDisplayName.mockResolvedValue({})
      const wrapper = mountView()
      await search(wrapper, 'old')

      // Act
      await wrapper.get(`input[aria-label="New alias for ${PLAYER.steam_id}"]`).setValue(' New Name ')
      await wrapper.get('tbody button').trigger('click')
      await flushPromises()

      // Assert
      expect(api.updatePlayerDisplayName).toHaveBeenCalledWith({
        steam_id: PLAYER.steam_id,
        display_name: 'New Name',
      })
      expect(wrapper.get('tbody').text()).toContain('New Name')
    })
  })
})
