import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import LogUploadForm from './LogUploadForm.vue'
import { useMatchCommandStore } from '../stores/matchCommand'
import { useMatchQueryStore } from '../stores/matchQuery'
import { usePlayerQueryStore } from '../stores/playerQuery'
import { useRatingQueryStore } from '../stores/ratingQuery'

vi.mock('../api', () => ({
  uploadLog: vi.fn(),
  fetchMatchDetail: vi.fn(),
}))

describe('LogUploadForm', () => {
  let router

  beforeEach(async () => {
    setActivePinia(createPinia())
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
    const commandStore = useMatchCommandStore()
    const queryStore = useMatchQueryStore()
    const playerStore = usePlayerQueryStore()
    const ratingStore = useRatingQueryStore()

    commandStore.submitLogUpload = vi.fn().mockResolvedValue({
      matchId: 'match-1',
      detail: { match_summary: { ratings_ready: true }, players: [] },
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
    await wrapper.vm.$nextTick()

    expect(commandStore.submitLogUpload).toHaveBeenCalled()
    expect(pushSpy).toHaveBeenCalledWith({
      name: 'match-stats',
      params: { matchId: 'match-1' },
    })
  })
})
