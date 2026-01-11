<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearToken } from './api'

const route = useRoute()
const router = useRouter()

const isAuthPage = computed(() => route.path === '/login' || route.path === '/register')

function logout() {
  clearToken()
  router.push('/login')
}
</script>

<template>
  <div style="max-width: 1100px; margin: 0 auto; padding: 16px; font-family: system-ui, -apple-system, Segoe UI, Roboto;">
    <header v-if="!isAuthPage" style="display:flex; gap:12px; align-items:center; justify-content:space-between; margin-bottom: 16px;">
      <nav style="display:flex; gap:12px;">
        <RouterLink to="/search">Search</RouterLink>
        <RouterLink to="/likes">Likes</RouterLink>
        <RouterLink to="/queue">Queue</RouterLink>
        <RouterLink to="/history">History</RouterLink>
        <RouterLink to="/cookie">Cookie</RouterLink>
      </nav>
      <button @click="logout">Logout</button>
    </header>

    <RouterView />
  </div>
</template>
