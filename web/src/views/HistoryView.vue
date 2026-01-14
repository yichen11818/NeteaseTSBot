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

onMounted(load)
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50">
    <!-- Header -->
    <div class="bg-white border-b border-gray-200 p-6">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Clock :size="28" class="text-green-600" />
          播放历史
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
      <p class="text-gray-600">查看您最近播放的音乐记录</p>
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
          <div class="text-red-600 text-sm">{{ error }}</div>
        </div>
      </div>
      
      <!-- Empty state -->
      <div v-else-if="!history.length" class="flex items-center justify-center h-64">
        <div class="text-center">
          <Clock :size="48" class="mx-auto text-gray-400 mb-4" />
          <div class="text-gray-600 text-lg mb-2">暂无播放记录</div>
          <div class="text-gray-500 text-sm">开始播放音乐后，这里会显示您的播放历史</div>
        </div>
      </div>
      
      <!-- History content -->
      <div v-else class="space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-medium text-gray-900">最近播放</h3>
          <span class="text-sm text-gray-500">共 {{ history.length }} 条记录</span>
        </div>
        
        <div class="bg-white rounded-lg border border-gray-200 divide-y divide-gray-100">
          <div
            v-for="track in history"
            :key="track.id"
            class="flex items-center gap-4 p-4 hover:bg-gray-50 transition-colors"
          >
            <!-- Album art placeholder -->
            <div class="w-12 h-12 bg-gray-200 rounded-lg flex-shrink-0 overflow-hidden">
              <div class="w-full h-full bg-gradient-to-br from-green-400 to-blue-500 flex items-center justify-center">
                <Music :size="20" class="text-white" />
              </div>
            </div>
            
            <!-- Track info -->
            <div class="flex-1 min-w-0">
              <div class="font-medium text-gray-900 truncate">{{ track.title }}</div>
              <div class="text-sm text-gray-500 truncate">{{ track.artist }}</div>
            </div>
            
            <!-- Play time -->
            <div class="flex flex-col items-end text-sm text-gray-500">
              <div class="flex items-center gap-1">
                <Calendar :size="14" />
                <span>{{ getRelativeTime(track.played_at) }}</span>
              </div>
              <div class="text-xs text-gray-400 mt-1">
                {{ formatDateTime(track.played_at) }}
              </div>
            </div>
            
            <!-- Actions -->
            <div class="flex items-center gap-2">
              <button
                @click="addToQueue(track)"
                class="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-full transition-colors"
                title="添加到队列"
              >
                <Plus :size="18" />
              </button>
              
              <button
                @click="playTrack(track)"
                class="p-2 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-full transition-colors"
                title="立即播放"
              >
                <Play :size="18" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
