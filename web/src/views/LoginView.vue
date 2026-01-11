<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiPost, setToken, type TokenResponse } from '../api'

const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')

async function submit() {
  error.value = ''
  try {
    const res = await apiPost<TokenResponse>('/auth/login', {
      username: username.value,
      password: password.value,
    })
    setToken(res.access_token)
    router.push('/search')
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}
</script>

<template>
  <h2>Login</h2>
  <div style="display:flex; flex-direction:column; gap:8px; max-width: 420px;">
    <input v-model="username" placeholder="username" />
    <input v-model="password" placeholder="password" type="password" />
    <button @click="submit">Login</button>
    <RouterLink to="/register">Register</RouterLink>
    <pre v-if="error" style="white-space:pre-wrap; color:#b00;">{{ error }}</pre>
  </div>
</template>
