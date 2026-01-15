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
    <div class="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 z-20 shadow-sm">
      <div class="flex items-center gap-4">
        <h1 class="text-2xl font-bold text-gray-900 tracking-tight flex items-center gap-2">
          <Heart :size="28" class="text-red-500" fill="currentColor" />
          我的喜欢
        </h1>
        <span class="text-sm text-gray-500 hidden md:inline-block border-l border-gray-200 pl-4 h-5 leading-5">
          显示您在网易云音乐中收藏的歌曲
        </span>
      </div>
      <button 
        @click="load"
        :disabled="loading"
        class="btn-secondary text-sm py-1.5 px-3"
      >
        <RefreshCw :size="16" :class="{ 'animate-spin': loading }" />
        <span class="hidden sm:inline">刷新</span>
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-4 md:px-6 py-4 md:py-6 pb-24 scrollbar-thin">
      <!-- Loading state -->
      <div v-if="loading && (!likes || !likes.songs)" class="h-64 flex items-center justify-center">
        <div class="flex flex-col items-center gap-3">
          <div class="animate-spin rounded-full h-8 w-8 border-2 border-red-500 border-t-transparent"></div>
          <div class="text-sm text-gray-500 font-medium">加载收藏中...</div>
        </div>
      </div>
      
      <!-- Error state -->
      <div v-else-if="error" class="bg-red-50 border border-red-200 rounded-xl p-4 text-center max-w-lg mx-auto my-8">
        <div class="flex items-center justify-center gap-2 text-red-800 font-medium mb-1">
          <AlertCircle :size="18" />
          加载失败
        </div>
        <div class="text-red-600 text-sm">{{ error }}</div>
        <div v-if="error.includes('Cookie')" class="mt-3">
          <RouterLink to="/cookie" class="btn-secondary text-xs bg-white text-red-600 border-red-200 hover:bg-red-50">前往设置页面配置 Cookie</RouterLink>
        </div>
      </div>
      
      <!-- Empty state -->
      <div v-else-if="likes && (!likes.songs || likes.songs.length === 0)" class="empty-state">
        <div class="w-20 h-20 bg-red-50 rounded-2xl flex items-center justify-center mb-6 text-red-500 shadow-sm">
          <Heart :size="40" fill="currentColor" />
        </div>
        <div class="text-gray-900 text-xl font-bold mb-2">暂无收藏歌曲</div>
        <div class="text-gray-500">去搜索页面发现更多音乐吧</div>
      </div>
      
      <!-- Likes content -->
      <div v-else-if="likes?.songs" class="max-w-6xl mx-auto space-y-4 fade-in">
        
        <div class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <table class="w-full text-left border-collapse">
            <thead class="bg-gray-50/50 text-gray-400 text-xs uppercase font-semibold border-b border-gray-100 hidden md:table-header-group">
              <tr>
                <th class="px-3 md:px-6 py-4 font-medium w-16">#</th>
                <th class="px-3 md:px-6 py-4 font-medium">标题</th>
                <th class="px-3 md:px-6 py-4 font-medium hidden md:table-cell">歌手</th>
                <th class="px-3 md:px-6 py-4 font-medium hidden lg:table-cell">专辑</th>
                <th class="px-3 md:px-6 py-4 font-medium w-24 text-right">时长</th>
                <th class="px-3 md:px-6 py-4 font-medium w-24"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <tr
                v-for="(song, index) in likes.songs"
                :key="song.id"
                class="group hover:bg-red-50/30 transition-colors duration-200"
              >
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-400 text-center font-medium group-hover:text-red-600 w-10 md:w-16">
                  {{ index + 1 }}
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4">
                  <div class="flex items-center gap-3 md:gap-4">
                    <!-- Thumbnail -->
                    <div class="w-10 h-10 rounded-lg overflow-hidden flex-shrink-0 relative group/cover shadow-sm">
                      <img 
                        v-if="song.al?.picUrl" 
                        :src="song.al.picUrl + '?param=100y100'" 
                        :alt="song.name"
                        class="w-full h-full object-cover"
                      />
                      <div v-else class="w-full h-full bg-gradient-to-br from-red-400 to-pink-500 flex items-center justify-center">
                        <Music :size="16" class="text-white/50" />
                      </div>
                      <div 
                        class="absolute inset-0 bg-black/10 opacity-0 group-hover/cover:opacity-100 flex items-center justify-center transition-all cursor-pointer backdrop-blur-[1px]"
                        @click="playTrack(song)"
                      >
                        <Play :size="16" class="text-white drop-shadow-md" fill="currentColor" />
                      </div>
                    </div>
                    
                    <div class="min-w-0">
                      <div class="font-semibold text-gray-900 line-clamp-1 text-sm group-hover:text-red-600 transition-colors">{{ song.name }}</div>
                      <div class="text-xs text-gray-500 md:hidden line-clamp-1 mt-0.5">
                        {{ (song.ar || []).map((a: any) => a.name).join(', ') }}
                      </div>
                    </div>
                  </div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-600 hidden md:table-cell">
                  <div class="truncate max-w-[150px]">{{ (song.ar || []).map((a: any) => a.name).join(', ') }}</div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-500 hidden lg:table-cell">
                  <div class="truncate max-w-[150px]">{{ song.al?.name }}</div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-right text-sm text-gray-400 font-mono tabular-nums">
                  {{ formatDuration(song.dt) }}
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-right">
                  <div class="flex items-center justify-end gap-2 md:opacity-0 group-hover:opacity-100 transition-all duration-200 md:transform md:translate-x-2 group-hover:translate-x-0">
                    <button
                      @click="addToQueue(song)"
                      class="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                      title="添加到队列"
                    >
                      <Plus :size="18" />
                    </button>
                    
                    <button
                      @click="playTrack(song)"
                      class="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="立即播放"
                    >
                      <Play :size="18" />
                    </button>
                    
                    <button class="p-2 text-red-500 bg-red-50 rounded-lg cursor-default shadow-sm hidden md:block">
                      <Heart :size="18" fill="currentColor" />
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
