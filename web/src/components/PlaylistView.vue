<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { 
  Play, 
  Pause, 
  Heart, 
  MoreVertical, 
  Clock, 
  Music,
  Plus,
  Search
} from 'lucide-vue-next'
import { apiGet, apiPost, apiDelete } from '../api'

interface Track {
  id: number
  title: string
  artist: string
  album?: string
  duration?: number
  artwork?: string
  isLiked?: boolean
}

const tracks = ref<Track[]>([])
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')
const selectedTracks = ref<Set<number>>(new Set())
const currentPlayingId = ref<number | null>(null)
let refreshTimer: number | null = null

// Filter tracks based on search
const filteredTracks = computed(() => {
  if (!searchQuery.value) return tracks.value
  
  const query = searchQuery.value.toLowerCase()
  return tracks.value.filter(track => 
    track.title.toLowerCase().includes(query) ||
    track.artist.toLowerCase().includes(query) ||
    track.album?.toLowerCase().includes(query)
  )
})

// Load playlist tracks
async function loadTracks() {
  loading.value = true
  error.value = ''
  
  try {
    tracks.value = await apiGet<Track[]>('/queue')
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  } finally {
    loading.value = false
  }
}

// Play specific track
async function playTrack(track: Track) {
  try {
    await apiPost(`/queue/${track.id}/play`, {})
    currentPlayingId.value = track.id
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

// Add track to queue
async function addToQueue(track: Track) {
  try {
    await apiPost('/queue/add', {
      title: track.title,
      artist: track.artist,
      album: track.album
    })
    await loadTracks()
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

// Remove track from queue
async function removeTrack(trackId: number) {
  try {
    await apiDelete(`/queue/${trackId}`)
    tracks.value = tracks.value.filter(t => t.id !== trackId)
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function deleteSelected() {
  const ids = Array.from(selectedTracks.value)
  if (!ids.length) return
  try {
    await Promise.all(ids.map(id => apiDelete(`/queue/${id}`)))
    tracks.value = tracks.value.filter(t => !selectedTracks.value.has(t.id))
    selectedTracks.value.clear()
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

// Toggle track like status
async function toggleLike(track: Track) {
  try {
    if (track.isLiked) {
      await apiPost(`/likes/${track.id}/remove`, {})
    } else {
      await apiPost(`/likes/${track.id}/add`, {})
    }
    track.isLiked = !track.isLiked
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

// Handle drag end - reorder tracks
function onDragEnd() {
  // Update track order on server
  updateTrackOrder()
}

async function updateTrackOrder() {
  try {
    const trackIds = tracks.value.map(t => t.id)
    await apiPost('/queue/reorder', { track_ids: trackIds })
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

// Select/deselect tracks
function toggleTrackSelection(trackId: number) {
  if (selectedTracks.value.has(trackId)) {
    selectedTracks.value.delete(trackId)
  } else {
    selectedTracks.value.add(trackId)
  }
}

// Select all tracks
function selectAll() {
  if (selectedTracks.value.size === filteredTracks.value.length) {
    selectedTracks.value.clear()
  } else {
    filteredTracks.value.forEach(track => selectedTracks.value.add(track.id))
  }
}

// Format duration
function formatDuration(seconds?: number): string {
  if (!seconds) return '--:--'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

onMounted(loadTracks)

onMounted(() => {
  refreshTimer = window.setInterval(() => {
    void loadTracks()
  }, 3000)
})

onUnmounted(() => {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50">
    <!-- Header -->
    <div class="bg-white border-b border-gray-200 p-6">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold text-gray-900">播放列表</h1>
        <div class="flex items-center gap-2">
          <button 
            @click="loadTracks"
            class="btn-secondary"
          >
            刷新
          </button>
          <button class="btn-primary">
            <Plus :size="16" class="mr-1" />
            添加歌曲
          </button>
        </div>
      </div>
      
      <!-- Search bar -->
      <div class="relative">
        <Search :size="20" class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索歌曲、艺术家或专辑..."
          class="input-field pl-10"
        />
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-hidden">
      <!-- Loading state -->
      <div v-if="loading" class="flex items-center justify-center h-full">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
      
      <!-- Error state -->
      <div v-else-if="error" class="p-6">
        <div class="bg-red-50 border border-red-200 rounded-lg p-4">
          <div class="text-red-800 font-medium">加载失败</div>
          <div class="text-red-600 text-sm mt-1">{{ error }}</div>
        </div>
      </div>
      
      <!-- Empty state -->
      <div v-else-if="!tracks.length" class="flex items-center justify-center h-full">
        <div class="text-center">
          <Music :size="48" class="mx-auto text-gray-400 mb-4" />
          <div class="text-gray-600 text-lg mb-2">播放列表为空</div>
          <div class="text-gray-500 text-sm">添加一些歌曲开始播放吧</div>
        </div>
      </div>
      
      <!-- Playlist content -->
      <div v-else class="h-full flex flex-col">
        <!-- Controls bar -->
        <div class="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
          <div class="flex items-center gap-4">
            <button 
              @click="selectAll"
              class="text-sm text-blue-600 hover:text-blue-700"
            >
              {{ selectedTracks.size === filteredTracks.length ? '取消全选' : '全选' }}
            </button>
            <span class="text-sm text-gray-500">
              共 {{ filteredTracks.length }} 首歌曲
            </span>
          </div>
          
          <div v-if="selectedTracks.size > 0" class="flex items-center gap-2">
            <span class="text-sm text-gray-600">已选择 {{ selectedTracks.size }} 首</span>
            <button @click.stop="deleteSelected" class="btn-secondary text-sm">删除选中</button>
          </div>
        </div>
        
        <!-- Track list -->
        <div class="flex-1 overflow-y-auto">
          <VueDraggable
            v-model="tracks"
            @end="onDragEnd"
            class="divide-y divide-gray-100"
          >
            <div
              v-for="(track, index) in filteredTracks"
              :key="track.id"
              :class="[
                'flex items-center gap-4 p-4 hover:bg-gray-50 transition-colors cursor-pointer group',
                selectedTracks.has(track.id) ? 'bg-blue-50' : '',
                currentPlayingId === track.id ? 'bg-green-50' : ''
              ]"
              @click="toggleTrackSelection(track.id)"
            >
              <!-- Drag handle & index -->
              <div class="flex items-center gap-3 w-12">
                <div class="drag-handle cursor-move opacity-0 group-hover:opacity-100 transition-opacity">
                  <div class="w-1 h-4 bg-gray-400 rounded-full"></div>
                </div>
                <span class="text-sm text-gray-500 min-w-[20px]">{{ index + 1 }}</span>
              </div>
              
              <!-- Checkbox -->
              <input
                type="checkbox"
                :checked="selectedTracks.has(track.id)"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                @click.stop="toggleTrackSelection(track.id)"
              />
              
              <!-- Album art -->
              <div class="w-12 h-12 bg-gray-200 rounded-lg flex-shrink-0 overflow-hidden">
                <img 
                  v-if="track.artwork" 
                  :src="track.artwork" 
                  :alt="track.title"
                  class="w-full h-full object-cover"
                />
                <div v-else class="w-full h-full bg-gradient-to-br from-blue-400 to-purple-500"></div>
              </div>
              
              <!-- Track info -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <div 
                    :class="[
                      'font-medium truncate',
                      currentPlayingId === track.id ? 'text-green-600' : 'text-gray-900'
                    ]"
                  >
                    {{ track.title }}
                  </div>
                  <Heart 
                    v-if="track.isLiked"
                    :size="16" 
                    class="text-red-500 flex-shrink-0"
                    fill="currentColor"
                  />
                </div>
                <div class="text-sm text-gray-500 truncate">{{ track.artist }}</div>
                <div v-if="track.album" class="text-xs text-gray-400 truncate">{{ track.album }}</div>
              </div>
              
              <!-- Duration -->
              <div class="flex items-center gap-2 text-sm text-gray-500">
                <Clock :size="14" />
                {{ formatDuration(track.duration) }}
              </div>
              
              <!-- Actions -->
              <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  @click.stop="toggleLike(track)"
                  :class="[
                    'p-2 rounded-full transition-colors',
                    track.isLiked ? 'text-red-500 hover:text-red-600' : 'text-gray-400 hover:text-gray-600'
                  ]"
                >
                  <Heart :size="16" :fill="track.isLiked ? 'currentColor' : 'none'" />
                </button>
                
                <button
                  @click.stop="playTrack(track)"
                  class="p-2 rounded-full text-gray-400 hover:text-blue-600 transition-colors"
                >
                  <Play v-if="currentPlayingId !== track.id" :size="16" />
                  <Pause v-else :size="16" />
                </button>
                
                <button class="p-2 rounded-full text-gray-400 hover:text-gray-600 transition-colors">
                  <MoreVertical :size="16" />
                </button>
              </div>
            </div>
          </VueDraggable>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.drag-handle {
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
