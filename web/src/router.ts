import { createRouter, createWebHashHistory, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import { DEMO_MODE } from './demoMode'
import SearchView from './views/SearchView.vue'
import LikesView from './views/LikesView.vue'
import FavoritesView from './views/FavoritesView.vue'
import PlaylistsView from './views/PlaylistsView.vue'
import PlaylistDetailView from './views/PlaylistDetailView.vue'
import QueueView from './views/QueueView.vue'
import HistoryView from './views/HistoryView.vue'
import LyricsView from './views/LyricsView.vue'
import SettingsView from './views/SettingsView.vue'
import LoginView from './views/LoginView.vue'
import ChangePasswordView from './views/ChangePasswordView.vue'
import { refreshAuth } from './auth'

export const router = createRouter({
  history: DEMO_MODE ? createWebHashHistory(import.meta.env.BASE_URL) : createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/search' },
    { path: '/search', component: SearchView },
    { path: '/likes', component: LikesView },
    { path: '/favorites', component: FavoritesView },
    { path: '/playlists', component: PlaylistsView },
    { path: '/playlist/:id', component: PlaylistDetailView },
    { path: '/queue', component: QueueView },
    { path: '/history', component: HistoryView },
    { path: '/login', name: 'login', component: LoginView, meta: { authPage: true } },
    { path: '/change-password', name: 'change-password', component: ChangePasswordView, meta: { authPage: true, requiresAuth: true } },
    { path: '/settings', component: SettingsView, meta: { requiresAuth: true } },
    { path: '/setup', redirect: { path: '/settings', query: { group: 'setup' } } },
    { path: '/cookie', redirect: { path: '/settings', query: { group: 'authorization' } } },
    { path: '/lyrics', component: LyricsView },
  ],
})

router.beforeEach(async (to: RouteLocationNormalized) => {
  const status = await refreshAuth(true)
  if (status.authenticated && status.must_change_password && to.name !== 'change-password') {
    return { name: 'change-password' }
  }
  if (to.meta.requiresAuth && !status.authenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && status.authenticated) {
    return status.must_change_password ? { name: 'change-password' } : '/settings'
  }
  return true
})
