import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import MatchaIngestor from './MatchaIngestor.vue'
import { createTestRouter } from '../../test/helpers'
import * as api from '../../api'

vi.mock('../../api', () => ({
  fetchMatchaSourceStatus: vi.fn(),
  ingestMatchaMatch: vi.fn(),
  pollMatcha: vi.fn(),
  fetchMatches: vi.fn(),
}))

async function mountComponent() {
  const router = createTestRouter()
  const wrapper = mount(MatchaIngestor, {
    global: {
      plugins: [router, createTestingPinia({ createSpy: vi.fn, stubActions: false })],
    },
  })
  await flushPromises()
  return wrapper
}

describe('MatchaIngestor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchMatchaSourceStatus.mockResolvedValue({ configured: true, reachable: true })
    api.fetchMatches.mockResolvedValue([])
  })

  it('shows the api-consumer status', async () => {
    const wrapper = await mountComponent()

    expect(wrapper.get('[data-test="matcha-status"]').text()).toBe('api-consumer online')
  })

  it('reports an unconfigured api-consumer', async () => {
    api.fetchMatchaSourceStatus.mockResolvedValue({ configured: false, reachable: false })

    const wrapper = await mountComponent()

    expect(wrapper.get('[data-test="matcha-status"]').text()).toBe('api-consumer not configured')
  })

  it('ingests one matcha.tf match and links the published matches', async () => {
    // Arrange
    api.ingestMatchaMatch.mockResolvedValue({
      accepted: 2,
      skipped: 0,
      noLogs: false,
      published: [{ matchId: 'aaaaaaaa-1111' }, { matchId: 'bbbbbbbb-2222' }],
    })
    const wrapper = await mountComponent()

    // Act
    await wrapper.get('input[type="number"]').setValue('201')
    await wrapper.get('[data-test="matcha-match-form"]').trigger('submit')
    await flushPromises()

    // Assert
    expect(api.ingestMatchaMatch).toHaveBeenCalledWith({ match_id: 201 })
    const result = wrapper.get('[data-test="matcha-result"]')
    expect(result.text()).toContain('matcha.tf match #201: 2 log(s) published, 0 already ingested')
    expect(result.findAll('a')).toHaveLength(2)
    expect(api.fetchMatches).toHaveBeenCalled()
  })

  it('says when a match has no logs yet', async () => {
    api.ingestMatchaMatch.mockResolvedValue({ accepted: 0, skipped: 0, noLogs: true, published: [] })
    const wrapper = await mountComponent()

    await wrapper.get('input[type="number"]').setValue('7')
    await wrapper.get('[data-test="matcha-match-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('matcha.tf match #7 has no logs.tf logs yet')
  })

  it('polls the configured league, optionally re-publishing', async () => {
    // Arrange
    api.pollMatcha.mockResolvedValue({
      matchIds: 5,
      accepted: 3,
      skipped: 1,
      noLogs: 1,
      failed: 0,
      failedMatchIds: [],
    })
    const wrapper = await mountComponent()
    await wrapper.get('input[type="checkbox"]').setValue(true)

    // Act
    await wrapper.get('[data-test="matcha-poll"]').trigger('click')
    await flushPromises()

    // Assert
    expect(api.pollMatcha).toHaveBeenCalledWith({ reset: true })
    expect(wrapper.text()).toContain('5 match(es) listed, 3 log(s) published, 1 skipped, 1 without logs, 0 failed')
  })

  it('shows proxy errors', async () => {
    api.pollMatcha.mockRejectedValue(new Error('503 Service Unavailable: api-consumer is unreachable'))
    const wrapper = await mountComponent()

    await wrapper.get('[data-test="matcha-poll"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('503 Service Unavailable: api-consumer is unreachable')
  })
})
