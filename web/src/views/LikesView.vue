<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiGet, apiPost } from '../api'
import { 
  Heart, 
  Play, 
  Plus, 
  Clock, 
  Music,
  RefreshCw,
  AlertCircle
} from 'lucide-vue-next'

const USER_COOKIE_KEY = 'tsbot_user_netease_cookie'

const error = ref('')
const likes = ref<any>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  likes.value = null
  
  try {
    const cookie = localStorage.getItem(USER_COOKIE_KEY) || ''
    if (!cookie) {
      throw new Error('需要先设置网易云音乐 Cookie')
    }
    likes.value = await apiGet<any>('/netease/likes', { 'X-Netease-Cookie': cookie })
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  } finally {
    loading.value = false
  }
}

async function playTrack(song: any) {
  try {
    const artist = (song.ar || []).map((a: any) => a.name).join(', ')
    await apiPost('/queue/netease', {
      song_id: String(song.id),
      title: song.name,
      artist,
      play_now: true,
    })
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function addToQueue(song: any) {
  try {
    const artist = (song.ar || []).map((a: any) => a.name).join(', ')
    await apiPost('/queue/netease', {
      song_id: String(song.id),
      title: song.name,
      artist,
      play_now: false,
    })
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

function formatDuration(duration: number): string {
  const minutes = Math.floor(duration / 60000)
  const seconds = Math.floor((duration % 60000) / 1000)
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

onMounted(load)
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50">
    <!-- Header -->
    <div class="bg-white border-b border-gray-200 p-6">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Heart :size="28" class="text-red-500" fill="currentColor" />
          我的喜欢
        </h1>
        <button 
          @click="load"
          :disabled="loading"
          class="btn-secondary flex items-center gap-2"
        >
          <RefreshCw :size="16" :class="{ 'animate-spin': loading }" />
          刷新
        </button>
      </div>
      <p class="text-gray-600">显示您在网易云音乐中收藏的歌曲</p>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-6">
      <!-- Loading state -->
      <div v-if="loading" class="flex items-center justify-center h-64">
        <div class="text-center">
          <RefreshCw :size="32" class="animate-spin text-blue-600 mx-auto mb-4" />
          <div class="text-gray-600">加载中...</div>
        </div>
      </div>
      
      <!-- Error state -->
      <div v-else-if="error" class="flex items-center justify-center h-64">
        <div class="text-center max-w-md">
          <AlertCircle :size="48" class="mx-auto text-red-500 mb-4" />
          <div class="text-red-800 font-medium mb-2">加载失败</div>
          <div class="text-red-600 text-sm mb-4">{{ error }}</div>
          <div v-if="error.includes('Cookie')" class="text-gray-600 text-sm">
            请前往设置页面配置您的网易云音乐 Cookie
          </div>
        </div>
      </div>
      
      <!-- Empty state -->
      <div v-else-if="likes && (!likes.songs || likes.songs.length === 0)" class="flex items-center justify-center h-64">
        <div class="text-center">
          <Heart :size="48" class="mx-auto text-gray-400 mb-4" />
          <div class="text-gray-600 text-lg mb-2">暂无收藏歌曲</div>
          <div class="text-gray-500 text-sm">去搜索页面发现更多音乐吧</div>
        </div>
      </div>
      
      <!-- Likes content -->
      <div v-else-if="likes?.songs" class="space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-medium text-gray-900">收藏的歌曲</h3>
          <span class="text-sm text-gray-500">共 {{ likes.songs.length }} 首</span>
        </div>
        
        <div class="bg-white rounded-lg border border-gray-200 divide-y divide-gray-100">
          <div
            v-for="song in likes.songs"
            :key="song.id"
            class="flex items-center gap-4 p-4 hover:bg-gray-50 transition-colors"
          >
            <!-- Album art -->
            <div class="w-12 h-12 bg-gray-200 rounded-lg flex-shrink-0 overflow-hidden">
              <img 
                v-if="song.al?.picUrl" 
                :src="song.al.picUrl + '?param=100y100'" 
                :alt="song.name"
                class="w-full h-full object-cover"
              />
              <div v-else class="w-full h-full bg-gradient-to-br from-red-400 to-pink-500"></div>
            </div>
            
            <!-- Song info -->
            <div class="flex-1 min-w-0">
              <div class="font-medium text-gray-900 truncate">{{ song.name }}</div>
              <div class="text-sm text-gray-500 truncate">
                {{ (song.ar || []).map((a: any) => a.name).join(', ') }}
              </div>
              <div v-if="song.al?.name" class="text-xs text-gray-400 truncate">
                {{ song.al.name }}
              </div>
            </div>
            
            <!-- Duration -->
            <div v-if="song.dt" class="flex items-center gap-1 text-sm text-gray-500">
              <Clock :size="14" />
              {{ formatDuration(song.dt) }}
            </div>
            
            <!-- Actions -->
            <div class="flex items-center gap-2">
              <button
                @click="addToQueue(song)"
                class="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-full transition-colors"
                title="添加到队列"
              >
                <Plus :size="18" />
              </button>
              
              <button
                @click="playTrack(song)"
                class="p-2 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-full transition-colors"
                title="立即播放"
              >
                <Play :size="18" />
              </button>
              
              <Heart :size="18" class="text-red-500" fill="currentColor" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
