<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiGet } from '../api'
import { 
  ListMusic, 
  RefreshCw, 
  AlertCircle,
  Music,
  User,
  Calendar
} from 'lucide-vue-next'

const USER_COOKIE_KEY = 'tsbot_user_netease_cookie'

const error = ref('')
const playlists = ref<any>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  playlists.value = null
  
  try {
    const cookie = localStorage.getItem(USER_COOKIE_KEY) || ''
    if (!cookie) {
      throw new Error('需要先设置网易云音乐 Cookie')
    }
    playlists.value = await apiGet<any>('/netease/playlists', { 'X-Netease-Cookie': cookie })
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  } finally {
    loading.value = false
  }
}

function formatDate(timestamp: number): string {
  return new Date(timestamp).toLocaleDateString('zh-CN')
}

onMounted(load)
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50">
    <!-- Header -->
    <div class="bg-white border-b border-gray-200 p-6">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <ListMusic :size="28" class="text-blue-600" />
          我的歌单
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
      <p class="text-gray-600">显示您在网易云音乐中创建和收藏的歌单</p>
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
      <div v-else-if="playlists && (!playlists.playlist || playlists.playlist.length === 0)" class="flex items-center justify-center h-64">
        <div class="text-center">
          <ListMusic :size="48" class="mx-auto text-gray-400 mb-4" />
          <div class="text-gray-600 text-lg mb-2">暂无歌单</div>
          <div class="text-gray-500 text-sm">去网易云音乐创建您的第一个歌单吧</div>
        </div>
      </div>
      
      <!-- Playlists content -->
      <div v-else-if="playlists?.playlist" class="space-y-6">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-medium text-gray-900">歌单列表</h3>
          <span class="text-sm text-gray-500">共 {{ playlists.playlist.length }} 个歌单</span>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          <div
            v-for="playlist in playlists.playlist"
            :key="playlist.id"
            class="bg-white rounded-lg border border-gray-200 overflow-hidden hover:shadow-md transition-shadow cursor-pointer"
          >
            <!-- Playlist cover -->
            <div class="aspect-square bg-gray-200 overflow-hidden">
              <img 
                v-if="playlist.coverImgUrl" 
                :src="playlist.coverImgUrl + '?param=300y300'" 
                :alt="playlist.name"
                class="w-full h-full object-cover"
              />
              <div v-else class="w-full h-full bg-gradient-to-br from-blue-400 to-purple-500 flex items-center justify-center">
                <Music :size="48" class="text-white" />
              </div>
            </div>
            
            <!-- Playlist info -->
            <div class="p-4">
              <h4 class="font-medium text-gray-900 truncate mb-2">{{ playlist.name }}</h4>
              
              <div class="space-y-1 text-sm text-gray-500">
                <div class="flex items-center gap-1">
                  <Music :size="14" />
                  <span>{{ playlist.trackCount }} 首歌曲</span>
                </div>
                
                <div class="flex items-center gap-1">
                  <User :size="14" />
                  <span class="truncate">{{ playlist.creator?.nickname || '未知' }}</span>
                </div>
                
                <div v-if="playlist.createTime" class="flex items-center gap-1">
                  <Calendar :size="14" />
                  <span>{{ formatDate(playlist.createTime) }}</span>
                </div>
              </div>
              
              <div v-if="playlist.description" class="mt-2 text-xs text-gray-400 line-clamp-2">
                {{ playlist.description }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
