import { createMemoryHistory, createRouter } from 'vue-router'

const Stub = { template: '<div />' }

/** Every named route the app links to, rendered as empty stubs. */
const NAMED_ROUTES = [
  { path: '/', name: 'tournament' },
  { path: '/event/:eventId?', name: 'event' },
  { path: '/match/:matchId?', name: 'match-stats' },
  { path: '/player/:steamId?', name: 'player-stats' },
  { path: '/auth/callback', name: 'auth-callback' },
  { path: '/admin/ingest', name: 'admin-ingest' },
  { path: '/admin/events', name: 'admin-events' },
  { path: '/admin/tournaments', name: 'admin-tournaments' },
  { path: '/admin/matches', name: 'admin-matches' },
  { path: '/admin/players', name: 'admin-players' },
]

/**
 * Memory-history router for component tests. Every app route name resolves,
 * so components can push/link by name without the real view tree.
 */
export function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: NAMED_ROUTES.map((route) => ({ ...route, component: Stub })),
  })
}

/** Build an unsigned JWT-shaped token carrying the given claims. */
export function fakeJwt(claims) {
  const encode = (value) => btoa(JSON.stringify(value)).replace(/=+$/, '')
  return `${encode({ alg: 'none' })}.${encode(claims)}.sig`
}
