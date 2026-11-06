import { createRouter, createWebHistory } from 'vue-router'
import TournamentView from './views/TournamentView.vue'
import MatchStatsView from './views/MatchStatsView.vue'
import PlayerStatsView from './views/PlayerStatsView.vue'
import EventView from './views/EventView.vue'
import AuthCallbackView from './views/AuthCallbackView.vue'
import AdminShell from './layouts/AdminShell.vue'
import AdminIngestView from './views/admin/AdminIngestView.vue'
import AdminEventsView from './views/admin/AdminEventsView.vue'
import AdminTournamentsView from './views/admin/AdminTournamentsView.vue'
import AdminMatchesView from './views/admin/AdminMatchesView.vue'
import AdminPlayersView from './views/admin/AdminPlayersView.vue'
import { useAuthStore } from './stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'tournament',
      component: TournamentView,
    },
    {
      path: '/event/:eventId?',
      name: 'event',
      component: EventView,
      props: true,
    },
    {
      path: '/match/:matchId?',
      name: 'match-stats',
      component: MatchStatsView,
      props: true,
    },
    // Legacy logId URLs redirect into the CQRS matchId route.
    {
      path: '/match-log/:logId',
      redirect: (to) => ({ name: 'match-stats', params: { matchId: String(to.params.logId) } }),
    },
    {
      path: '/player/:steamId?',
      name: 'player-stats',
      component: PlayerStatsView,
      props: true,
    },
    {
      path: '/auth/callback',
      name: 'auth-callback',
      component: AuthCallbackView,
      meta: { public: true },
    },
    {
      path: '/admin',
      component: AdminShell,
      meta: { requiresAuth: true, requiresAdmin: true },
      children: [
        { path: '', redirect: { name: 'admin-ingest' } },
        { path: 'ingest', name: 'admin-ingest', component: AdminIngestView },
        { path: 'events', name: 'admin-events', component: AdminEventsView },
        { path: 'tournaments', name: 'admin-tournaments', component: AdminTournamentsView },
        { path: 'matches', name: 'admin-matches', component: AdminMatchesView },
        { path: 'players', name: 'admin-players', component: AdminPlayersView },
      ],
    },
    // Legacy bookmark for the pre-split single-page admin dashboard.
    {
      path: '/admin/dashboard',
      redirect: { name: 'admin-ingest' },
    },
  ],
})

/**
 * Global navigation guard: restores the session from a stored token, sends
 * anonymous users to Steam login for protected routes, and keeps non-admins
 * out of `/admin/*`.
 * @param {import('vue-router').RouteLocationNormalized} to
 */
export async function authGuard(to) {
  const auth = useAuthStore()
  if (!auth.user && auth.token) {
    await auth.bootstrap()
  }

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    auth.beginSteamLogin()
    return false
  }

  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'tournament' }
  }

  return true
}

router.beforeEach(authGuard)

export default router
