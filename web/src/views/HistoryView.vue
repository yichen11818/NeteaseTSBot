<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiGet } from '../api'

const error = ref('')
const items = ref<any[]>([])

async function load() {
  error.value = ''
  try {
    items.value = await apiGet<any[]>('/history')
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

onMounted(load)
</script>

<template>
  <h2>History</h2>
  <button @click="load">Reload</button>
  <pre v-if="error" style="white-space:pre-wrap; color:#b00;">{{ error }}</pre>

  <table v-if="items.length" style="width:100%; margin-top: 12px; border-collapse: collapse;">
    <thead>
      <tr>
        <th style="text-align:left; border-bottom:1px solid #ddd; padding:6px;">Played at</th>
        <th style="text-align:left; border-bottom:1px solid #ddd; padding:6px;">Title</th>
        <th style="text-align:left; border-bottom:1px solid #ddd; padding:6px;">By</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="it in items" :key="it.id">
        <td style="border-bottom:1px solid #eee; padding:6px;">{{ it.played_at }}</td>
        <td style="border-bottom:1px solid #eee; padding:6px;">{{ it.title }}</td>
        <td style="border-bottom:1px solid #eee; padding:6px;">{{ it.requested_by }}</td>
      </tr>
    </tbody>
  </table>
</template>
