<script setup lang="ts">
import { ref } from 'vue'
import { apiGet, apiPost } from '../api'

const keywords = ref('')
const error = ref('')
const songs = ref<any[]>([])

async function search() {
  error.value = ''
  songs.value = []
  try {
    const res = await apiGet<{ raw: any }>(`/search?keywords=${encodeURIComponent(keywords.value)}&limit=20`)
    const list = res?.raw?.result?.songs || []
    songs.value = list
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function enqueue(song: any) {
  error.value = ''
  try {
    const urlRes = await apiGet<any>(`/me/netease/song/url?id=${encodeURIComponent(String(song.id))}`)
    const data = urlRes?.data?.[0]
    if (!data?.url) throw new Error('no playable url (maybe need cookie or vip)')

    await apiPost('/queue', {
      track_id: String(song.id),
      title: song.name,
      artist: (song.ar || []).map((a: any) => a.name).join(', '),
      source_url: data.url,
    })
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}
</script>

<template>
  <h2>Search</h2>
  <div style="display:flex; gap:8px; align-items:center;">
    <input v-model="keywords" placeholder="keywords" style="flex:1;" />
    <button @click="search">Search</button>
  </div>

  <pre v-if="error" style="white-space:pre-wrap; color:#b00;">{{ error }}</pre>

  <table v-if="songs.length" style="width:100%; margin-top: 12px; border-collapse: collapse;">
    <thead>
      <tr>
        <th style="text-align:left; border-bottom:1px solid #ddd; padding:6px;">Title</th>
        <th style="text-align:left; border-bottom:1px solid #ddd; padding:6px;">Artist</th>
        <th style="text-align:left; border-bottom:1px solid #ddd; padding:6px;">Actions</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="s in songs" :key="s.id">
        <td style="border-bottom:1px solid #eee; padding:6px;">{{ s.name }}</td>
        <td style="border-bottom:1px solid #eee; padding:6px;">{{ (s.ar || []).map((a:any)=>a.name).join(', ') }}</td>
        <td style="border-bottom:1px solid #eee; padding:6px;">
          <button @click="enqueue(s)">Add to queue</button>
        </td>
      </tr>
    </tbody>
  </table>
</template>
