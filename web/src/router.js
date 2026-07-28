import { createRouter, createWebHistory } from 'vue-router'
import TournamentView from './views/TournamentView.vue'
import MatchStatsView from './views/MatchStatsView.vue'
import PlayerStatsView from './views/PlayerStatsView.vue'
import AuthCallbackView from './views/AuthCallbackView.vue'
import AdminDashboardView from './views/AdminDashboardView.vue'
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
      path: '/admin/dashboard',
      name: 'admin-dashboard',
      component: AdminDashboardView,
      meta: { requiresAuth: true, requiresAdmin: true },
    },
  ],
})

router.beforeEach(async (to) => {
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
})

export default router
