<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiGet, apiPost } from '../api'
import { 
  Clock, 
  Play, 
  Plus, 
  RefreshCw, 
  AlertCircle,
  Music,
  Calendar
} from 'lucide-vue-next'

const error = ref('')
const history = ref<any[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  
  try {
    history.value = await apiGet<any[]>('/history')
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  } finally {
    loading.value = false
  }
}

async function playTrack(track: any) {
  try {
    await apiPost(`/history/${track.id}/replay?play_now=true`)
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function addToQueue(track: any) {
  try {
    await apiPost(`/history/${track.id}/replay?play_now=false`)
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

function formatDateTime(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function getRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffHours / 24)
  
  if (diffHours < 1) return '刚刚'
  if (diffHours < 24) return `${diffHours}小时前`
  if (diffDays < 7) return `${diffDays}天前`
  return formatDateTime(dateString)
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
          <Clock :size="28" class="text-green-600" />
          最近播放
        </h1>
        <span class="text-sm text-gray-500 hidden md:inline-block border-l border-gray-200 pl-4 h-5 leading-5">
          记录您最近收听的 200 首歌曲
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
      <div v-if="loading && !history.length" class="h-64 flex items-center justify-center">
        <div class="flex flex-col items-center gap-3">
          <div class="animate-spin rounded-full h-8 w-8 border-2 border-green-600 border-t-transparent"></div>
          <div class="text-sm text-gray-500 font-medium">加载记录中...</div>
        </div>
      </div>
      
      <!-- Error state -->
      <div v-else-if="error" class="bg-red-50 border border-red-200 rounded-xl p-4 text-center max-w-lg mx-auto my-8">
        <div class="flex items-center justify-center gap-2 text-red-800 font-medium mb-1">
          <AlertCircle :size="18" />
          加载失败
        </div>
        <div class="text-red-600 text-sm">{{ error }}</div>
      </div>
      
      <!-- Empty state -->
      <div v-else-if="!history.length" class="empty-state">
        <div class="w-20 h-20 bg-green-50 rounded-2xl flex items-center justify-center mb-6 text-green-500 shadow-sm">
          <Clock :size="40" />
        </div>
        <div class="text-gray-900 text-xl font-bold mb-2">暂无播放记录</div>
        <div class="text-gray-500">开始播放音乐后，这里会显示您的播放历史</div>
      </div>
      
      <!-- History content -->
      <div v-else class="max-w-6xl mx-auto space-y-4 fade-in">
        
        <div class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <table class="w-full text-left border-collapse">
            <thead class="bg-gray-50/50 text-gray-400 text-xs uppercase font-semibold border-b border-gray-100 hidden md:table-header-group">
              <tr>
                <th class="px-3 md:px-6 py-4 font-medium w-16">#</th>
                <th class="px-3 md:px-6 py-4 font-medium">标题</th>
                <th class="px-3 md:px-6 py-4 font-medium hidden md:table-cell">歌手</th>
                <th class="px-3 md:px-6 py-4 font-medium hidden lg:table-cell">专辑</th>
                <th class="px-3 md:px-6 py-4 font-medium w-32 text-right">播放时间</th>
                <th class="px-3 md:px-6 py-4 font-medium w-24"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <tr
                v-for="(track, index) in history"
                :key="track.id"
                class="group hover:bg-green-50/30 transition-colors duration-200"
              >
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-400 text-center font-medium group-hover:text-green-600 w-10 md:w-16">
                  {{ index + 1 }}
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4">
                  <div class="flex items-center gap-3 md:gap-4">
                    <!-- Thumbnail -->
                    <div class="w-10 h-10 rounded-lg overflow-hidden flex-shrink-0 relative group/cover shadow-sm">
                      <img 
                        v-if="track.artwork" 
                        :src="track.artwork + '?param=100y100'" 
                        :alt="track.title"
                        class="w-full h-full object-cover"
                      />
                      <div v-else class="w-full h-full bg-gradient-to-br from-green-100 to-emerald-100 flex items-center justify-center">
                        <Music :size="16" class="text-green-600/50" />
                      </div>
                      <div 
                        class="absolute inset-0 bg-black/10 opacity-0 group-hover/cover:opacity-100 flex items-center justify-center transition-all cursor-pointer backdrop-blur-[1px]"
                        @click="playTrack(track)"
                      >
                        <Play :size="16" class="text-white drop-shadow-md" fill="currentColor" />
                      </div>
                    </div>
                    
                    <div class="min-w-0">
                      <div class="font-semibold text-gray-900 line-clamp-1 text-sm group-hover:text-green-700 transition-colors">{{ track.title }}</div>
                      <div class="text-xs text-gray-500 md:hidden line-clamp-1 mt-0.5">
                        {{ track.artist }}
                      </div>
                    </div>
                  </div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-600 hidden md:table-cell">
                  <div class="truncate max-w-[150px]">{{ track.artist }}</div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-500 hidden lg:table-cell">
                  <div class="truncate max-w-[150px]">{{ track.album }}</div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-right">
                  <div class="flex flex-col items-end">
                    <span class="text-xs font-medium text-gray-600 group-hover:text-green-700">{{ getRelativeTime(track.played_at) }}</span>
                    <span class="text-[10px] text-gray-400 font-mono mt-0.5">{{ formatDateTime(track.played_at).split(' ')[1] }}</span>
                  </div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-right">
                  <div class="flex items-center justify-end gap-2 md:opacity-0 group-hover:opacity-100 transition-all duration-200 md:transform md:translate-x-2 group-hover:translate-x-0">
                    <button
                      @click="addToQueue(track)"
                      class="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                      title="添加到队列"
                    >
                      <Plus :size="18" />
                    </button>
                    <button
                      @click="playTrack(track)"
                      class="p-2 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                      title="立即播放"
                    >
                      <Play :size="18" />
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
