import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import LogUploadForm from './LogUploadForm.vue'
import { useMatchQueryStore } from '../../stores/matchQuery'
import { usePlayerQueryStore } from '../../stores/playerQuery'
import { useRatingQueryStore } from '../../stores/ratingQuery'
import * as api from '../../api'

vi.mock('../../api', () => ({
  uploadLog: vi.fn(),
  ingestLogsTf: vi.fn(),
  fetchMatchDetail: vi.fn(),
}))

describe('LogUploadForm', () => {
  let router

  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', name: 'home', component: { template: '<div />' } },
        { path: '/match/:matchId?', name: 'match-stats', component: { template: '<div />' } },
      ],
    })
    await router.push('/')
    await router.isReady()
  })

  function mountForm() {
    return mount(LogUploadForm, {
      global: {
        plugins: [router],
      },
    })
  }

  it('disables submit when log data is empty', () => {
    const wrapper = mountForm()
    const button = wrapper.get('button[type="submit"]')
    expect(button.attributes('disabled')).toBeDefined()
  })

  it('enables submit when log data is present', async () => {
    const wrapper = mountForm()
    await wrapper.get('textarea').setValue('map_name=cp_process_final')
    const button = wrapper.get('button[type="submit"]')
    expect(button.attributes('disabled')).toBeUndefined()
  })

  it('submits upload and navigates on success', async () => {
    const queryStore = useMatchQueryStore()
    const playerStore = usePlayerQueryStore()
    const ratingStore = useRatingQueryStore()

    api.uploadLog.mockResolvedValue({ match_id: 'match-1', status: 'accepted' })
    api.fetchMatchDetail.mockResolvedValue({
      match_summary: { ratings_ready: true },
      players: [],
    })
    queryStore.invalidateMatch = vi.fn()
    queryStore.loadMatches = vi.fn().mockResolvedValue([])
    queryStore.loadMatchDetail = vi.fn().mockResolvedValue({})
    playerStore.clear = vi.fn()
    ratingStore.invalidate = vi.fn()

    const pushSpy = vi.spyOn(router, 'push')
    const wrapper = mountForm()
    await wrapper.get('textarea').setValue('map_name=cp_process_final blu_score=1 red_score=0')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(api.uploadLog).toHaveBeenCalled()
    expect(api.fetchMatchDetail).toHaveBeenCalledWith('match-1')
    expect(pushSpy).toHaveBeenCalledWith({
      name: 'match-stats',
      params: { matchId: 'match-1' },
    })
  })

  it('includes tournament_id when the prop is set', async () => {
    api.uploadLog.mockResolvedValue({ match_id: 'match-2', status: 'skipped' })
    const wrapper = mount(LogUploadForm, {
      props: { tournamentId: 'tourney-1' },
      global: { plugins: [router] },
    })
    await wrapper.get('textarea').setValue('map_name=cp_process_final')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(api.uploadLog).toHaveBeenCalledWith(
      expect.objectContaining({
        log_data: 'map_name=cp_process_final',
        tournament_id: 'tourney-1',
      }),
    )
  })
})
