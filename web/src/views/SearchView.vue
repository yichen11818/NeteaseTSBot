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
import EmptyState from '../components/EmptyState.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'

const keywords = ref('')
const error = ref('')
const status = ref('')
const songs = ref<any[]>([])
const loading = ref(false)
const suggestions = ref<string[]>([])
const hotSearches = ref<any[]>([])
const showSuggestions = ref(false)
const defaultKeyword = ref('')

async function search() {
  if (!keywords.value.trim()) return
  
  loading.value = true
  error.value = ''
  status.value = ''
  songs.value = []
  showSuggestions.value = false
  
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

async function getSuggestions() {
  if (!keywords.value.trim()) {
    suggestions.value = []
    showSuggestions.value = false
    return
  }
  
  try {
    const res = await apiGet<any>(`/netease/search/suggest?keywords=${encodeURIComponent(keywords.value)}`)
    const suggests = res?.result?.allMatch || []
    suggestions.value = suggests.map((item: any) => item.keyword || item.name || item).slice(0, 8)
    showSuggestions.value = suggestions.value.length > 0
  } catch (e) {
    suggestions.value = []
    showSuggestions.value = false
  }
}

async function loadHotSearches() {
  try {
    const res = await apiGet<any>('/netease/search/hot')
    hotSearches.value = res?.result?.hots || []
  } catch (e) {
    hotSearches.value = []
  }
}

async function loadDefaultKeyword() {
  try {
    const res = await apiGet<any>('/netease/search/default')
    defaultKeyword.value = res?.data?.showKeyword || res?.data?.realkeyword || ''
  } catch (e) {
    defaultKeyword.value = ''
  }
}

function selectSuggestion(suggestion: string) {
  keywords.value = suggestion
  showSuggestions.value = false
  search()
}

function selectHotSearch(hotItem: any) {
  keywords.value = hotItem.first || hotItem.keyword || hotItem
  search()
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

function handleInput() {
  getSuggestions()
}

function handleFocus() {
  if (keywords.value.trim()) {
    getSuggestions()
  }
}

function handleBlur() {
  // 延迟隐藏建议，允许点击建议项
  setTimeout(() => {
    showSuggestions.value = false
  }, 200)
}

// 页面加载时初始化
import { onMounted } from 'vue'

onMounted(() => {
  loadHotSearches()
  loadDefaultKeyword()
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50">
    <!-- Header -->
    <div class="bg-white/80 backdrop-blur-md border-b border-gray-200 px-6 py-4 sticky top-0 z-30 shadow-sm transition-all duration-300">
      <h1 class="text-2xl font-bold text-gray-900 mb-4 flex items-center gap-2">
        <Search :size="28" class="text-blue-600" />
        搜索音乐
      </h1>
      
      <!-- Search bar -->
      <div class="relative max-w-2xl">
        <div class="relative group">
          <Search :size="20" class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 group-focus-within:text-blue-500 transition-colors" />
          <input
            v-model="keywords"
            type="text"
            :placeholder="defaultKeyword ? `试试搜索: ${defaultKeyword}` : '搜索歌曲、艺术家或专辑...'"
            class="w-full pl-10 pr-24 py-3 bg-gray-100/50 border border-gray-200 rounded-xl text-gray-900 focus:bg-white focus:ring-2 focus:ring-blue-100 focus:border-blue-500 outline-none transition-all duration-200 placeholder-gray-400 text-sm font-medium"
            @keypress="handleKeyPress"
            @input="handleInput"
            @focus="handleFocus"
            @blur="handleBlur"
          />
          <button
            @click="search"
            :disabled="loading || !keywords.trim()"
            class="absolute right-2 top-1/2 transform -translate-y-1/2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
          >
            <Loader2 v-if="loading" :size="16" class="animate-spin" />
            <span v-else>搜索</span>
          </button>
        </div>
        
        <!-- Search suggestions -->
        <div 
          v-if="showSuggestions && suggestions.length > 0"
          class="absolute top-full left-0 right-0 mt-2 bg-white/95 backdrop-blur-xl border border-gray-100/50 rounded-xl shadow-xl z-50 max-h-[320px] overflow-y-auto py-2 ring-1 ring-black/5"
        >
          <div
            v-for="suggestion in suggestions"
            :key="suggestion"
            @click="selectSuggestion(suggestion)"
            class="px-4 py-2.5 hover:bg-blue-50/50 cursor-pointer flex items-center gap-3 group transition-colors"
          >
            <Search :size="16" class="text-gray-400 group-hover:text-blue-500" />
            <span class="text-gray-700 group-hover:text-gray-900">{{ suggestion }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-4 md:px-6 py-4 md:py-6 pb-24 scrollbar-thin">
      <!-- Status messages -->
      <div v-if="error" class="mb-6 bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-3 text-red-700">
        <div class="font-medium">搜索失败</div>
        <div class="text-sm opacity-90 border-l border-red-200 pl-3">{{ error }}</div>
      </div>
      
      <div v-if="status" class="mb-6 bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-3 text-green-700 status-success shadow-sm">
        <div class="font-medium">{{ status }}</div>
      </div>
      
      <!-- Loading state -->
      <div v-if="loading" class="h-64 flex items-center justify-center">
         <LoadingSpinner :size="40" text="正在搜索..." />
      </div>
      
      <!-- Empty state -->
      <EmptyState
        v-else-if="!songs.length && !error && keywords && !loading"
        :icon="Music"
        title="未找到相关歌曲"
        description="尝试使用不同的关键词搜索"
        action-text="清除搜索条件"
        @action="keywords = ''"
      />
      
      <!-- Initial state -->
      <div v-else-if="!songs.length && !keywords" class="space-y-8 max-w-4xl mx-auto mt-4">
        <div class="text-center py-8">
           <div class="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mx-auto mb-4 text-blue-500">
             <Search :size="32" />
           </div>
           <h2 class="text-lg font-bold text-gray-900">开始搜索音乐</h2>
           <p class="text-gray-500 text-sm mt-1">发现百万首好歌</p>
        </div>
        
        <!-- Hot searches -->
        <div v-if="hotSearches.length > 0">
          <h3 class="text-sm font-bold text-gray-900 uppercase tracking-wider mb-4 flex items-center gap-2">
            <span class="w-1 h-4 bg-red-500 rounded-full"></span>
            热门搜索
          </h3>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="(hotItem, index) in hotSearches.slice(0, 20)"
              :key="index"
              @click="selectHotSearch(hotItem)"
              class="group px-4 py-2 bg-white border border-gray-100 hover:border-blue-200 hover:bg-blue-50/50 text-gray-700 rounded-full transition-all duration-200 text-sm flex items-center gap-2"
            >
              <span class="font-bold text-xs" :class="index < 3 ? 'text-red-500' : 'text-gray-400'">{{ index + 1 }}</span>
              <span class="group-hover:text-blue-600">{{ hotItem.first || hotItem.keyword || hotItem }}</span>
            </button>
          </div>
        </div>
      </div>
      
      <!-- Search results -->
      <div v-else class="max-w-6xl mx-auto space-y-4 fade-in">
        <div class="flex items-center justify-between px-1">
          <h3 class="text-lg font-bold text-gray-900">搜索结果</h3>
          <span class="text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded-md font-mono">
            {{ songs.length }} results
          </span>
        </div>
        
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
                v-for="(song, index) in songs"
                :key="song.id"
                class="group hover:bg-blue-50/30 transition-colors duration-200"
              >
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-400 text-center font-medium group-hover:text-blue-600 w-10 md:w-16">
                  {{ index + 1 }}
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4">
                  <div class="flex items-center gap-3 md:gap-4">
                    <!-- Thumbnail -->
                    <div class="w-10 h-10 rounded-lg overflow-hidden flex-shrink-0 relative group/cover shadow-sm bg-gray-100">
                      <img 
                        v-if="song.al?.picUrl || song.album?.picUrl || (song.artists && song.artists[0]?.img1v1Url)" 
                        :src="(song.al?.picUrl || song.album?.picUrl || song.artists?.[0]?.img1v1Url) + '?param=100y100'" 
                        :alt="song.name"
                        class="w-full h-full object-cover"
                      />
                      <div v-else class="w-full h-full bg-gradient-to-br from-blue-100 to-indigo-100 flex items-center justify-center">
                        <Music :size="16" class="text-blue-400" />
                      </div>
                      <div 
                        class="absolute inset-0 bg-black/10 opacity-0 group-hover/cover:opacity-100 flex items-center justify-center transition-all cursor-pointer backdrop-blur-[1px]"
                        @click="enqueue(song, true)"
                      >
                        <Play :size="16" class="text-white drop-shadow-md" fill="currentColor" />
                      </div>
                    </div>
                    
                    <div class="min-w-0">
                      <div class="font-semibold text-gray-900 line-clamp-1 text-sm group-hover:text-blue-600 transition-colors" :title="song.name">{{ song.name }}</div>
                      <div class="text-xs text-gray-500 md:hidden line-clamp-1 mt-0.5">
                        {{ ((song.ar || song.artists) || []).map((a: any) => a.name).join(', ') }}
                      </div>
                    </div>
                  </div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-600 hidden md:table-cell">
                   <div class="truncate max-w-[150px]" :title="((song.ar || song.artists) || []).map((a: any) => a.name).join(', ')">
                      {{ ((song.ar || song.artists) || []).map((a: any) => a.name).join(', ') }}
                   </div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-500 hidden lg:table-cell">
                  <div class="truncate max-w-[150px]" :title="song.al?.name || song.album?.name">{{ song.al?.name || song.album?.name }}</div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-right text-sm text-gray-400 font-mono tabular-nums">
                  {{ song.dt || song.duration ? formatDuration(song.dt || song.duration) : '--:--' }}
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-right">
                  <div class="flex items-center justify-end gap-2 md:opacity-0 group-hover:opacity-100 transition-all duration-200 md:transform md:translate-x-2 group-hover:translate-x-0">
                    <button
                      @click="enqueue(song, false)"
                      class="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                      title="添加到队列"
                    >
                      <Plus :size="18" />
                    </button>
                    
                    <button
                      class="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="收藏"
                    >
                      <Heart :size="18" />
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
