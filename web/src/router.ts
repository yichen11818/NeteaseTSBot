import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import SearchView from './views/SearchView.vue'
import LikesView from './views/LikesView.vue'
import PlaylistsView from './views/PlaylistsView.vue'
import QueueView from './views/QueueView.vue'
import HistoryView from './views/HistoryView.vue'
import CookieView from './views/CookieView.vue'
import LyricsView from './views/LyricsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/search' },
    { path: '/search', component: SearchView },
    { path: '/likes', component: LikesView },
    { path: '/playlists', component: PlaylistsView },
    { path: '/queue', component: QueueView },
    { path: '/history', component: HistoryView },
    { path: '/cookie', component: CookieView },
    { path: '/lyrics', component: LyricsView },
  ],
})

router.beforeEach((_to: RouteLocationNormalized) => {
  return true
})
