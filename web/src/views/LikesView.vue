<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiGet } from '../api'

const error = ref('')
const likelist = ref<any>(null)

async function load() {
  error.value = ''
  likelist.value = null
  try {
    likelist.value = await apiGet<any>('/me/netease/likelist')
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

onMounted(load)
</script>

<template>
  <h2>My Likes (netease)</h2>
  <p>Requires your netease cookie.</p>
  <button @click="load">Reload</button>
  <pre v-if="error" style="white-space:pre-wrap; color:#b00;">{{ error }}</pre>

  <pre v-if="likelist" style="white-space:pre-wrap;">{{ JSON.stringify(likelist, null, 2) }}</pre>
</template>
