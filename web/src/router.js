import { createRouter, createWebHistory } from 'vue-router'
import TournamentView from './views/TournamentView.vue'
import MatchStatsView from './views/MatchStatsView.vue'
import PlayerStatsView from './views/PlayerStatsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'tournament',
      component: TournamentView,
    },
    {
      path: '/match/:logId?',
      name: 'match-stats',
      component: MatchStatsView,
      props: true,
    },
    {
      path: '/player/:steamId?',
      name: 'player-stats',
      component: PlayerStatsView,
      props: true,
    },
  ],
})

export default router
