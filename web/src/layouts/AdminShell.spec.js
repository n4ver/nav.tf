import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import AdminShell from './AdminShell.vue'
import { createTestRouter } from '../test/helpers'

vi.mock('../api', () => ({
  fetchAuthMe: vi.fn(),
  getSteamLoginUrl: vi.fn(() => '/login'),
}))

async function mountShell(path, auth) {
  const router = createTestRouter()
  await router.push(path)
  await router.isReady()
  return mount(AdminShell, {
    global: {
      plugins: [router, createTestingPinia({ createSpy: vi.fn, initialState: { auth } })],
      stubs: { RouterView: true },
    },
  })
}

const ADMIN = { token: 'tok', user: { role: 'ADMIN', steam_id: '765611', display_name: 'Boss' } }

describe('AdminShell', () => {
  it('shows who is signed in (carried over from the old admin dashboard)', async () => {
    const wrapper = await mountShell('/admin/ingest', ADMIN)

    const identity = wrapper.get('[data-test="admin-identity"]').text()
    expect(identity).toContain('Boss')
    expect(identity).toContain('765611')
  })

  it('marks the current admin section tab with aria-current', async () => {
    // Arrange / Act
    const wrapper = await mountShell('/admin/matches', ADMIN)

    // Assert
    const current = wrapper.findAll('nav [aria-current="page"]')
    expect(current).toHaveLength(1)
    expect(current[0].text()).toBe('Matches')
  })

  it('renders a tab for every admin section', async () => {
    const wrapper = await mountShell('/admin/ingest', ADMIN)

    expect(wrapper.findAll('nav a').map((tab) => tab.text())).toEqual([
      'Ingest',
      'Events',
      'Tournaments',
      'Matches',
      'Players',
    ])
  })
})
