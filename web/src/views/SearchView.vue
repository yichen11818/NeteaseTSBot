<script setup lang="ts">
import { ref } from 'vue'
import { apiGet, apiPost } from '../api'
import { 
  Search, 
  Play, 
  Plus, 
  Heart, 
  Clock,
  Music,
  Loader2
} from 'lucide-vue-next'

const keywords = ref('')
const error = ref('')
const status = ref('')
const songs = ref<any[]>([])
const loading = ref(false)

async function search() {
  if (!keywords.value.trim()) return
  
  loading.value = true
  error.value = ''
  status.value = ''
  songs.value = []
  
  try {
    const res = await apiGet<{ raw: any }>(`/search?keywords=${encodeURIComponent(keywords.value)}&limit=20`)
    const list = res?.raw?.result?.songs || []
    songs.value = list
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  } finally {
    loading.value = false
  }
}

async function enqueue(song: any, playNow: boolean) {
  error.value = ''
  status.value = ''
  try {
    const artist = ((song.ar || song.artists) || []).map((a: any) => a.name).join(', ')
    const res = await apiPost<{ ok: boolean; id: number; source_url: string }>('/queue/netease', {
      song_id: String(song.id),
      title: song.name,
      artist,
      play_now: playNow,
    })
    status.value = `已添加到播放队列 #${res.id}${playNow ? ' (正在播放)' : ''}`
    
    // Clear status after 3 seconds
    setTimeout(() => {
      status.value = ''
    }, 3000)
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

function formatDuration(duration: number): string {
  const minutes = Math.floor(duration / 60000)
  const seconds = Math.floor((duration % 60000) / 1000)
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

function handleKeyPress(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    search()
  }
}
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50">
    <!-- Header -->
    <div class="bg-white border-b border-gray-200 p-6">
      <h1 class="text-2xl font-bold text-gray-900 mb-6">搜索音乐</h1>
      
      <!-- Search bar -->
      <div class="relative">
        <Search :size="20" class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
        <input
          v-model="keywords"
          type="text"
          placeholder="搜索歌曲、艺术家或专辑..."
          class="input-field pl-10 pr-20"
          @keypress="handleKeyPress"
        />
        <button
          @click="search"
          :disabled="loading || !keywords.trim()"
          class="absolute right-2 top-1/2 transform -translate-y-1/2 btn-primary px-4 py-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Loader2 v-if="loading" :size="16" class="animate-spin" />
          <span v-else>搜索</span>
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-6">
      <!-- Status messages -->
      <div v-if="error" class="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
        <div class="text-red-800 font-medium">搜索失败</div>
        <div class="text-red-600 text-sm mt-1">{{ error }}</div>
      </div>
      
      <div v-if="status" class="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg">
        <div class="text-green-800">{{ status }}</div>
      </div>
      
      <!-- Loading state -->
      <div v-if="loading" class="flex items-center justify-center h-64">
        <div class="text-center">
          <Loader2 :size="32" class="animate-spin text-blue-600 mx-auto mb-4" />
          <div class="text-gray-600">搜索中...</div>
        </div>
      </div>
      
      <!-- Empty state -->
      <div v-else-if="!songs.length && !error && keywords" class="flex items-center justify-center h-64">
        <div class="text-center">
          <Music :size="48" class="mx-auto text-gray-400 mb-4" />
          <div class="text-gray-600 text-lg mb-2">未找到相关歌曲</div>
          <div class="text-gray-500 text-sm">尝试使用不同的关键词搜索</div>
        </div>
      </div>
      
      <!-- Initial state -->
      <div v-else-if="!songs.length && !keywords" class="flex items-center justify-center h-64">
        <div class="text-center">
          <Search :size="48" class="mx-auto text-gray-400 mb-4" />
          <div class="text-gray-600 text-lg mb-2">开始搜索音乐</div>
          <div class="text-gray-500 text-sm">输入歌曲名、艺术家或专辑名称</div>
        </div>
      </div>
      
      <!-- Search results -->
      <div v-else class="space-y-2">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-medium text-gray-900">搜索结果</h3>
          <span class="text-sm text-gray-500">找到 {{ songs.length }} 首歌曲</span>
        </div>
        
        <div class="bg-white rounded-lg border border-gray-200 divide-y divide-gray-100">
          <div
            v-for="song in songs"
            :key="song.id"
            class="flex items-center gap-4 p-4 hover:bg-gray-50 transition-colors"
          >
            <!-- Album art -->
            <div class="w-12 h-12 bg-gray-200 rounded-lg flex-shrink-0 overflow-hidden">
              <img 
                v-if="song.al?.picUrl || song.album?.picUrl || (song.artists && song.artists[0]?.img1v1Url)" 
                :src="(song.al?.picUrl || song.album?.picUrl || song.artists?.[0]?.img1v1Url) + '?param=100y100'" 
                :alt="song.name"
                class="w-full h-full object-cover"
              />
              <div v-else class="w-full h-full bg-gradient-to-br from-blue-400 to-purple-500"></div>
            </div>
            
            <!-- Song info -->
            <div class="flex-1 min-w-0">
              <div class="font-medium text-gray-900 truncate">{{ song.name }}</div>
              <div class="text-sm text-gray-500 truncate">
                {{ ((song.ar || song.artists) || []).map((a: any) => a.name).join(', ') }}
              </div>
              <div v-if="song.al?.name || song.album?.name" class="text-xs text-gray-400 truncate">
                {{ song.al?.name || song.album?.name }}
              </div>
            </div>
            
            <!-- Duration -->
            <div v-if="song.dt || song.duration" class="flex items-center gap-1 text-sm text-gray-500">
              <Clock :size="14" />
              {{ formatDuration(song.dt || song.duration) }}
            </div>
            
            <!-- Actions -->
            <div class="flex items-center gap-2">
              <button
                @click="enqueue(song, false)"
                class="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-full transition-colors"
                title="添加到队列"
              >
                <Plus :size="18" />
              </button>
              
              <button
                @click="enqueue(song, true)"
                class="p-2 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-full transition-colors"
                title="立即播放"
              >
                <Play :size="18" />
              </button>
              
              <button
                class="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-full transition-colors"
                title="添加到喜欢"
              >
                <Heart :size="18" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
