<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiGet, apiPost } from '../api'
import { 
  ListMusic, 
  RefreshCw, 
  AlertCircle,
  Music,
  User,
  Calendar,
  Play,
  Plus,
  Heart,
  TrendingUp,
  Star
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'

const router = useRouter()
const error = ref('')
const status = ref('')
const loading = ref(false)
const categories = ref<any[]>([])
const selectedCategory = ref('全部')
const playlists = ref<any[]>([])
const highQualityPlaylists = ref<any[]>([])
const recommendPlaylists = ref<any[]>([])

async function loadCategories() {
  try {
    const res = await apiGet<any>('/netease/playlist/categories')
    categories.value = res?.sub || []
  } catch (e) {
    console.error('Failed to load categories:', e)
  }
}

async function loadPlaylists(cat: string = '全部') {
  loading.value = true
  error.value = ''
  
  try {
    const [topRes, highQualityRes, recommendRes] = await Promise.all([
      apiGet<any>(`/netease/playlist/top?cat=${encodeURIComponent(cat)}&limit=30`),
      apiGet<any>(`/netease/playlist/highquality?cat=${encodeURIComponent(cat)}&limit=10`),
      apiGet<any>('/netease/recommend/playlists?limit=10')
    ])
    
    playlists.value = topRes?.playlists || []
    highQualityPlaylists.value = highQualityRes?.playlists || []
    recommendPlaylists.value = recommendRes?.result || []
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  } finally {
    loading.value = false
  }
}

async function selectCategory(cat: string) {
  selectedCategory.value = cat
  await loadPlaylists(cat)
}

function goToPlaylist(id: number | string) {
  router.push(`/playlist/${id}`)
}

async function addPlaylistToQueue(playlist: any) {
  error.value = ''
  status.value = ''
  
  try {
    // 获取歌单详情
    const detailRes = await apiGet<any>(`/netease/playlist/${playlist.id}/detail`)
    const tracks = detailRes?.playlist?.tracks || []
    
    if (tracks.length === 0) {
      error.value = '歌单为空或无法获取歌曲'
      return
    }
    
    // 弹窗确认
    const songsToAdd = tracks.slice(0, 5)
    const confirmed = confirm(`确定要将歌单《${playlist.name}》的前 ${songsToAdd.length} 首歌曲添加到播放队列吗？\n\n歌单共有 ${tracks.length} 首歌曲，将添加前 ${songsToAdd.length} 首。`)
    
    if (!confirmed) {
      return
    }
    
    let addedCount = 0
    
    for (const track of songsToAdd) {
      try {
        const artist = (track.ar || track.artists || []).map((a: any) => a.name).join(', ')
        await apiPost('/queue/netease', {
          song_id: String(track.id),
          title: track.name,
          artist,
          play_now: false,
        })
        addedCount++
      } catch (e) {
        console.error('Failed to add track:', e)
      }
    }
    
    status.value = `已添加 ${addedCount} 首歌曲到播放队列`
    setTimeout(() => {
      status.value = ''
    }, 3000)
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

function formatPlayCount(count: number): string {
  if (count >= 100000000) {
    return `${(count / 100000000).toFixed(1)}亿`
  } else if (count >= 10000) {
    return `${(count / 10000).toFixed(1)}万`
  }
  return count.toString()
}

onMounted(() => {
  loadCategories()
  loadPlaylists()
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50">
    <!-- Header -->
    <div class="bg-white/80 backdrop-blur-md border-b border-gray-200 px-6 py-4 sticky top-0 z-20 shadow-sm transition-all duration-300">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold text-gray-900 flex items-center gap-3">
          <ListMusic :size="28" class="text-blue-600" />
          发现歌单
        </h1>
        <button 
          @click="loadPlaylists(selectedCategory)"
          :disabled="loading"
          class="btn-secondary text-sm py-1.5 px-3"
        >
          <RefreshCw :size="16" :class="{ 'animate-spin': loading }" />
          <span class="hidden sm:inline">刷新</span>
        </button>
      </div>
      
      <!-- Category filter -->
      <div v-if="categories.length > 0" class="flex flex-wrap gap-2">
        <button
          @click="selectCategory('全部')"
          class="px-4 py-1.5 text-sm rounded-full transition-all duration-200 font-medium border"
          :class="[
            selectedCategory === '全部' 
              ? 'bg-blue-600 text-white border-blue-600 shadow-md shadow-blue-200' 
              : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50 hover:border-gray-300'
          ]"
        >
          全部
        </button>
        <button
          v-for="category in categories.slice(0, 15)"
          :key="category.name"
          @click="selectCategory(category.name)"
          class="px-4 py-1.5 text-sm rounded-full transition-all duration-200 font-medium border"
          :class="[
            selectedCategory === category.name 
              ? 'bg-blue-600 text-white border-blue-600 shadow-md shadow-blue-200' 
              : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50 hover:border-gray-300'
          ]"
        >
          {{ category.name }}
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-4 py-4 md:px-6 md:py-6 pb-24 scrollbar-thin">
      <!-- Status messages -->
      <div v-if="error" class="mb-6 bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-3 text-red-700">
        <AlertCircle :size="20" class="flex-shrink-0" />
        <div>
          <div class="font-medium">加载失败</div>
          <div class="text-sm opacity-90">{{ error }}</div>
        </div>
      </div>
      
      <div v-if="status" class="mb-6 bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-3 text-green-700 status-success shadow-sm">
        <div class="font-medium">{{ status }}</div>
      </div>
      
      <!-- Loading state -->
      <div v-if="loading && !playlists.length" class="h-64 flex items-center justify-center">
        <LoadingSpinner text="正在加载歌单..." />
      </div>
      
      <!-- Content sections -->
      <div v-else class="space-y-10 max-w-[1600px] mx-auto">
        <!-- High quality playlists -->
        <section v-if="highQualityPlaylists.length > 0" class="fade-in">
          <h2 class="text-xl font-bold text-gray-900 mb-5 flex items-center gap-2">
            <Star :size="24" class="text-yellow-500 fill-yellow-500" />
            精品歌单
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 md:gap-6">
            <div
              v-for="playlist in highQualityPlaylists"
              :key="playlist.id"
              class="group relative flex flex-col gap-3 cursor-pointer"
              @click="goToPlaylist(playlist.id)"
            >
              <div class="relative aspect-square rounded-xl overflow-hidden shadow-sm transition-all duration-300 group-hover:shadow-xl group-hover:-translate-y-1">
                <img 
                  :src="playlist.coverImgUrl + '?param=300y300'" 
                  :alt="playlist.name"
                  class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                />
                <!-- Hover Overlay -->
                <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center backdrop-blur-[2px]">
                   <div 
                    class="w-12 h-12 bg-white/90 rounded-full flex items-center justify-center text-blue-600 shadow-lg transform scale-50 group-hover:scale-100 transition-transform duration-300 hover:bg-white hover:scale-110"
                    @click.stop="addPlaylistToQueue(playlist)"
                    title="添加到播放队列"
                  >
                    <Play :size="24" fill="currentColor" class="ml-1" />
                  </div>
                </div>
                <!-- Play Count Badge -->
                <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Play :size="10" fill="currentColor" />
                  {{ formatPlayCount(playlist.playCount) }}
                </div>
              </div>
              
              <div class="min-w-0">
                <h3 class="font-bold text-gray-900 text-sm line-clamp-2 leading-snug group-hover:text-blue-600 transition-colors mb-1" :title="playlist.name">
                  {{ playlist.name }}
                </h3>
                <p class="text-xs text-gray-500 flex items-center gap-1 truncate">
                  <User :size="12" />
                  {{ playlist.creator?.nickname }}
                </p>
              </div>
            </div>
          </div>
        </section>

        <!-- Recommended playlists -->
        <section v-if="recommendPlaylists.length > 0" class="fade-in">
          <h2 class="text-xl font-bold text-gray-900 mb-5 flex items-center gap-2">
            <TrendingUp :size="24" class="text-green-500" />
            推荐歌单
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 md:gap-6">
            <div
              v-for="playlist in recommendPlaylists"
              :key="playlist.id"
              class="group relative flex flex-col gap-3 cursor-pointer"
              @click="goToPlaylist(playlist.id)"
            >
              <div class="relative aspect-square rounded-xl overflow-hidden shadow-sm transition-all duration-300 group-hover:shadow-xl group-hover:-translate-y-1">
                <img 
                  :src="playlist.picUrl + '?param=300y300'" 
                  :alt="playlist.name"
                  class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                />
                 <!-- Hover Overlay -->
                <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center backdrop-blur-[2px]">
                   <div 
                    class="w-12 h-12 bg-white/90 rounded-full flex items-center justify-center text-green-600 shadow-lg transform scale-50 group-hover:scale-100 transition-transform duration-300 hover:bg-white hover:scale-110"
                    @click.stop="addPlaylistToQueue(playlist)"
                    title="添加到播放队列"
                  >
                    <Play :size="24" fill="currentColor" class="ml-1" />
                  </div>
                </div>
                <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Play :size="10" fill="currentColor" />
                  {{ formatPlayCount(playlist.playCount) }}
                </div>
              </div>
              <div class="min-w-0">
                <h3 class="font-bold text-gray-900 text-sm line-clamp-2 leading-snug group-hover:text-green-600 transition-colors mb-1" :title="playlist.name">
                  {{ playlist.name }}
                </h3>
              </div>
            </div>
          </div>
        </section>

        <!-- All playlists -->
        <section v-if="playlists.length > 0" class="fade-in">
          <h2 class="text-xl font-bold text-gray-900 mb-5 flex items-center gap-2">
            <ListMusic :size="24" class="text-blue-500" />
            {{ selectedCategory }} 歌单
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 md:gap-6">
            <div
              v-for="playlist in playlists"
              :key="playlist.id"
              class="group relative flex flex-col gap-3 cursor-pointer"
              @click="goToPlaylist(playlist.id)"
            >
              <div class="relative aspect-square rounded-xl overflow-hidden shadow-sm transition-all duration-300 group-hover:shadow-xl group-hover:-translate-y-1">
                <img 
                  :src="playlist.coverImgUrl + '?param=300y300'" 
                  :alt="playlist.name"
                  class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                />
                 <!-- Hover Overlay -->
                <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center backdrop-blur-[2px]">
                   <div 
                    class="w-12 h-12 bg-white/90 rounded-full flex items-center justify-center text-blue-600 shadow-lg transform scale-50 group-hover:scale-100 transition-transform duration-300 hover:bg-white hover:scale-110"
                    @click.stop="addPlaylistToQueue(playlist)"
                    title="添加到播放队列"
                  >
                    <Play :size="24" fill="currentColor" class="ml-1" />
                  </div>
                </div>
                <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Play :size="10" fill="currentColor" />
                  {{ formatPlayCount(playlist.playCount) }}
                </div>
              </div>
              
              <div class="min-w-0">
                <h3 class="font-bold text-gray-900 text-sm line-clamp-2 leading-snug group-hover:text-blue-600 transition-colors mb-1" :title="playlist.name">
                  {{ playlist.name }}
                </h3>
                <p class="text-xs text-gray-500 flex items-center gap-1 truncate">
                  <User :size="12" />
                  {{ playlist.creator?.nickname }}
                </p>
              </div>
            </div>
          </div>
        </section>

        <!-- Empty state -->
        <EmptyState
          v-if="!loading && playlists.length === 0 && highQualityPlaylists.length === 0 && recommendPlaylists.length === 0"
          :icon="ListMusic"
          title="暂无歌单"
          description="尝试选择其他分类或刷新页面"
        />
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
