import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AdminIngestView from './AdminIngestView.vue'
import LogUploadForm from '../../components/admin/LogUploadForm.vue'
import LogsTfIngestor from '../../components/admin/LogsTfIngestor.vue'
import { createTestRouter } from '../../test/helpers'
import * as api from '../../api'

vi.mock('../../api', () => ({
  fetchEvents: vi.fn(),
  fetchTournaments: vi.fn(),
}))

async function mountView() {
  const router = createTestRouter()
  await router.push('/admin/ingest')
  const wrapper = mount(AdminIngestView, {
    global: {
      plugins: [router, createTestingPinia({ createSpy: vi.fn })],
      stubs: { LogUploadForm: true, LogsTfIngestor: true, MatchaIngestor: true },
    },
  })
  await flushPromises()
  return wrapper
}

describe('AdminIngestView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchEvents.mockResolvedValue([])
  })

  it('lists tournaments as ingest targets with a default option', async () => {
    // Arrange
    api.fetchTournaments.mockResolvedValue([
      { tournament_id: 't-1', name: 'Invite', slug: 'invite' },
      { tournament_id: 't-2', name: 'Open', slug: 'open' },
    ])

    // Act
    const wrapper = await mountView()

    // Assert
    const options = wrapper.findAll('option').map((option) => option.text())
    expect(options).toEqual(['Default tournament', 'Invite (invite)', 'Open (open)'])
  })

  it('prefixes tournaments with their event name', async () => {
    api.fetchEvents.mockResolvedValue([{ event_id: 'e-1', name: 'Season One' }])
    api.fetchTournaments.mockResolvedValue([
      { tournament_id: 't-1', name: 'Invite', slug: 'invite', event_id: 'e-1' },
    ])

    const wrapper = await mountView()

    const options = wrapper.findAll('option').map((option) => option.text())
    expect(options).toEqual(['Default tournament', 'Season One - Invite (invite)'])
  })

  it('offers matcha.tf ingest through the api-consumer', async () => {
    api.fetchTournaments.mockResolvedValue([])

    const wrapper = await mountView()

    expect(wrapper.findComponent({ name: 'MatchaIngestor' }).exists()).toBe(true)
    expect(wrapper.text()).toContain('Ingest from matcha.tf (api-consumer)')
  })

  it('passes the selected tournament to both ingest forms', async () => {
    // Arrange
    api.fetchTournaments.mockResolvedValue([{ tournament_id: 't-1', name: 'Invite', slug: 'invite' }])
    const wrapper = await mountView()

    // Act
    await wrapper.get('select').setValue('t-1')

    // Assert
    expect(wrapper.getComponent(LogUploadForm).props('tournamentId')).toBe('t-1')
    expect(wrapper.getComponent(LogsTfIngestor).props('tournamentId')).toBe('t-1')
  })

  it('shows an error when tournaments fail to load', async () => {
    api.fetchTournaments.mockRejectedValue(new Error('503 Service Unavailable'))

    const wrapper = await mountView()

    expect(wrapper.get('[role="alert"]').text()).toContain('503 Service Unavailable')
  })
})
