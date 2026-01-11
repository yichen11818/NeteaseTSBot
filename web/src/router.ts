import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import LoginView from './views/LoginView.vue'
import RegisterView from './views/RegisterView.vue'
import SearchView from './views/SearchView.vue'
import LikesView from './views/LikesView.vue'
import QueueView from './views/QueueView.vue'
import HistoryView from './views/HistoryView.vue'
import CookieView from './views/CookieView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/search' },
    { path: '/login', component: LoginView },
    { path: '/register', component: RegisterView },
    { path: '/search', component: SearchView },
    { path: '/likes', component: LikesView },
    { path: '/queue', component: QueueView },
    { path: '/history', component: HistoryView },
    { path: '/cookie', component: CookieView },
  ],
})

router.beforeEach((to: RouteLocationNormalized) => {
  const token = localStorage.getItem('tsbot_token')
  if (!token && to.path !== '/login' && to.path !== '/register') {
    return '/login'
  }
  return true
})
