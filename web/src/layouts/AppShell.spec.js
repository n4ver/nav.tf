import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AppShell from './AppShell.vue'
import { createTestRouter } from '../test/helpers'
import * as api from '../api'

vi.mock('../api', () => ({
  fetchAuthMe: vi.fn(),
  fetchQueryHealth: vi.fn(),
  getSteamLoginUrl: vi.fn(() => '/login'),
  searchQuery: vi.fn(),
}))

async function mountShell() {
  const router = createTestRouter()
  await router.push('/')
  await router.isReady()
  const wrapper = mount(AppShell, {
    slots: { default: '<p data-test="page">Page body</p>' },
    global: { plugins: [router, createTestingPinia({ createSpy: vi.fn })] },
  })
  return wrapper
}

describe('AppShell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the top nav, a skip link and the page inside the main landmark', async () => {
    // Arrange
    api.fetchQueryHealth.mockResolvedValue({ status: 'ok' })

    // Act
    const wrapper = await mountShell()

    // Assert
    expect(wrapper.find('header nav[aria-label="Primary"]').exists()).toBe(true)
    expect(wrapper.get('a[href="#main-content"]').text()).toBe('Skip to content')
    expect(wrapper.get('main#main-content').find('[data-test="page"]').exists()).toBe(true)
  })

  describe('API status footer', () => {
    it('reports checking before the health call resolves', async () => {
      api.fetchQueryHealth.mockReturnValue(new Promise(() => {}))

      const wrapper = await mountShell()

      expect(wrapper.get('[data-test="api-status"]').text()).toBe('Checking API…')
    })

    it('reports online when the query service is healthy', async () => {
      api.fetchQueryHealth.mockResolvedValue({ status: 'ok', side: 'query' })

      const wrapper = await mountShell()
      await flushPromises()

      expect(wrapper.get('[data-test="api-status"]').text()).toBe('API online')
    })

    it('reports unavailable when the health call fails', async () => {
      api.fetchQueryHealth.mockRejectedValue(new Error('502 Bad Gateway'))

      const wrapper = await mountShell()
      await flushPromises()

      expect(wrapper.get('[data-test="api-status"]').text()).toBe('API unavailable')
    })
  })
})
