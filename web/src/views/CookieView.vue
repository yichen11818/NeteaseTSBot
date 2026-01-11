<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiGet, apiPut } from '../api'

const cookie = ref('')
const status = ref('')

async function load() {
  status.value = ''
  const data = await apiGet<{ cookie: string }>('/me/netease/cookie')
  cookie.value = data.cookie
}

async function save() {
  status.value = ''
  try {
    await apiPut('/me/netease/cookie', { cookie: cookie.value })
    status.value = 'saved'
  } catch (e: any) {
    status.value = String(e?.message ?? e)
  }
}

onMounted(load)
</script>

<template>
  <h2>Netease Cookie</h2>
  <p>Paste your netease cookie here (stored encrypted in local sqlite). This cookie is per-user.</p>
  <textarea v-model="cookie" rows="8" style="width:100%;"></textarea>
  <div style="margin-top: 8px; display:flex; gap:8px;">
    <button @click="save">Save</button>
    <button @click="load">Reload</button>
  </div>
  <pre v-if="status" style="white-space:pre-wrap;">{{ status }}</pre>
</template>
