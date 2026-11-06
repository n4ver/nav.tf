import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import AdminEventsView from './AdminEventsView.vue'
import * as api from '../../api'

vi.mock('../../api', () => ({
  fetchEvents: vi.fn(),
  createEvent: vi.fn(),
  updateEvent: vi.fn(),
}))

describe('AdminEventsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    api.fetchEvents.mockResolvedValue([])
  })

  it('creates an event and reloads the catalog', async () => {
    api.createEvent.mockResolvedValue({
      event_id: 'event-1',
      name: 'Mini',
      slug: 'mini',
      status: 'accepted',
    })
    api.fetchEvents
      .mockResolvedValueOnce([])
      .mockResolvedValue([{ event_id: 'event-1', name: 'Mini', slug: 'mini', tournament_count: 0 }])

    const wrapper = mount(AdminEventsView, {
      global: {
        plugins: [
          createRouter({
            history: createMemoryHistory(),
            routes: [{ path: '/', component: { template: '<div />' } }],
          }),
        ],
      },
    })
    await flushPromises()

    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('Mini')
    await inputs[1].setValue('mini')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(api.createEvent).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Mini', slug: 'mini' }),
    )
    expect(wrapper.text()).toContain('Mini')
  })
})
