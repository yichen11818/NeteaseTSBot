<template>
  <div class="h-full flex flex-col bg-gray-50">
    <!-- Header -->
    <div class="bg-white/80 backdrop-blur-md border-b border-gray-200 px-4 md:px-6 py-3 md:py-4 sticky top-0 z-20 shadow-sm transition-all duration-300">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-xl md:text-2xl font-bold text-gray-900 flex items-center gap-2">
          <ListMusic :size="24" class="text-blue-600 md:w-7 md:h-7" />
          播放队列
        </h1>
        <div class="flex items-center gap-2">
          <button 
            @click="loadTracks"
            class="btn-secondary text-sm py-1.5 px-3"
            :disabled="loading"
          >
            <RefreshCw :size="16" :class="{ 'animate-spin': loading }" />
            <span class="hidden sm:inline">刷新</span>
          </button>
          <button class="btn-primary text-sm py-1.5 px-3 shadow-sm">
            <Plus :size="16" />
            <span class="hidden sm:inline">添加歌曲</span>
          </button>
        </div>
      </div>
      
      <!-- Search bar -->
      <div class="relative">
        <Search :size="18" class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="在队列中搜索..."
          class="w-full pl-10 pr-4 py-2 bg-gray-100 border-transparent focus:bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-100 rounded-lg text-sm transition-all duration-200 outline-none"
        />
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-hidden flex flex-col">
      <!-- Loading state -->
      <div v-if="loading && !tracks.length" class="flex items-center justify-center flex-1">
        <LoadingSpinner text="加载队列中..." />
      </div>
      
      <!-- Error state -->
      <div v-else-if="error" class="p-6">
        <div class="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-3 text-red-700">
          <AlertCircle :size="20" />
          <div>
            <div class="font-medium">加载失败</div>
            <div class="text-sm mt-1 opacity-90">{{ error }}</div>
          </div>
        </div>
      </div>
      
      <!-- Empty state -->
      <EmptyState
        v-else-if="!tracks.length"
        :icon="Music"
        title="播放列表为空"
        description="添加一些歌曲开始播放吧"
      />
      
      <!-- Playlist content -->
      <div v-else class="flex-1 flex flex-col min-h-0">
        <!-- Controls bar -->
        <div class="bg-gray-50 border-b border-gray-200 px-4 md:px-6 py-2 flex items-center justify-between text-xs text-gray-500">
          <div class="flex items-center gap-4">
            <button 
              @click="selectAll"
              class="hover:text-blue-600 transition-colors font-medium"
            >
              {{ selectedTracks.size === filteredTracks.length ? '取消全选' : '全选' }}
            </button>
            <span>
              共 {{ filteredTracks.length }} 首歌曲
            </span>
          </div>
          
          <div v-if="selectedTracks.size > 0" class="flex items-center gap-3 animate-fade-in">
            <span class="font-medium text-gray-700">已选择 {{ selectedTracks.size }} 首</span>
            <button 
              @click.stop="deleteSelected" 
              class="text-red-600 hover:text-red-700 hover:bg-red-50 px-2 py-1 rounded transition-colors flex items-center gap-1"
            >
              <Trash2 :size="14" />
              删除
            </button>
          </div>
        </div>
        
        <!-- Track list -->
        <div class="flex-1 overflow-y-auto scrollbar-thin px-2 md:px-6 pb-24 pt-2">
          <VueDraggable
            v-model="tracks"
            @start="onDragStart"
            @end="onDragEnd"
            class="space-y-1"
            handle=".drag-handle"
          >
            <div
              v-for="(track, index) in filteredTracks"
              :key="track.id"
              :class="[
                'flex items-center gap-2 md:gap-3 p-2 rounded-lg transition-all duration-200 border border-transparent group',
                currentPlayingId === track.id ? 'bg-blue-50/80 border-blue-100 shadow-sm' : 'hover:bg-white hover:border-gray-200 hover:shadow-sm',
                selectedTracks.has(track.id) ? 'bg-blue-50 border-blue-200' : ''
              ]"
              @click="toggleTrackSelection(track.id)"
            >
              <!-- Drag handle & index -->
              <div class="flex items-center gap-2 w-8 md:w-10 flex-shrink-0 justify-center">
                <div class="drag-handle cursor-grab active:cursor-grabbing text-gray-300 hover:text-gray-500 p-1">
                  <GripVertical :size="16" />
                </div>
              </div>
              
              <!-- Checkbox -->
              <div class="flex-shrink-0" @click.stop>
                <input
                  type="checkbox"
                  :checked="selectedTracks.has(track.id)"
                  class="rounded border-gray-300 text-blue-600 focus:ring-blue-500 w-4 h-4 cursor-pointer"
                  @change="toggleTrackSelection(track.id)"
                />
              </div>
              
              <!-- Album art -->
              <div class="w-10 h-10 rounded-md flex-shrink-0 overflow-hidden relative shadow-sm group/cover">
                <img 
                  v-if="track.artwork" 
                  :src="track.artwork" 
                  :alt="track.title"
                  class="w-full h-full object-cover"
                />
                <div v-else class="w-full h-full bg-gradient-to-br from-blue-400 to-indigo-400 flex items-center justify-center">
                   <Music :size="16" class="text-white/50" />
                </div>
                
                <!-- Play Overlay -->
                 <div 
                  class="absolute inset-0 bg-black/20 opacity-0 group-hover/cover:opacity-100 flex items-center justify-center transition-all cursor-pointer backdrop-blur-[1px]"
                  @click.stop="playTrack(track)"
                >
                  <Play v-if="currentPlayingId !== track.id" :size="16" class="text-white drop-shadow-md" fill="currentColor" />
                  <div v-else class="flex gap-0.5 items-end h-3">
                     <div class="w-1 bg-white animate-music-bar-1"></div>
                     <div class="w-1 bg-white animate-music-bar-2"></div>
                     <div class="w-1 bg-white animate-music-bar-3"></div>
                  </div>
                </div>
              </div>
              
              <!-- Track info -->
              <div class="flex-1 min-w-0 flex flex-col justify-center">
                <div class="flex items-center gap-2">
                  <div 
                    :class="[
                      'font-medium truncate text-sm',
                      currentPlayingId === track.id ? 'text-blue-600' : 'text-gray-900'
                    ]"
                  >
                    {{ track.title }}
                  </div>
                </div>
                <div class="text-xs text-gray-500 truncate flex items-center gap-1">
                   <span>{{ track.artist }}</span>
                   <span v-if="track.album" class="w-0.5 h-0.5 bg-gray-400 rounded-full hidden sm:block"></span>
                   <span v-if="track.album" class="truncate opacity-80 hidden sm:block">{{ track.album }}</span>
                </div>
              </div>
              
              <!-- Duration -->
              <div class="hidden md:flex items-center text-xs text-gray-400 font-mono w-12 justify-end">
                {{ formatDuration(track.duration) }}
              </div>
              
              <!-- Actions -->
              <div class="flex items-center gap-1 md:opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  @click.stop="toggleLike(track)"
                  :class="[
                    'p-1.5 rounded-lg transition-colors',
                    track.isLiked ? 'text-red-500 bg-red-50' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
                  ]"
                >
                  <Heart :size="16" :fill="track.isLiked ? 'currentColor' : 'none'" />
                </button>
                
                <button
                  @click.stop="removeTrack(track.id)"
                  class="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                  title="从队列移除"
                >
                  <Trash2 :size="16" />
                </button>
              </div>
            </div>
          </VueDraggable>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { 
  Play, 
  Pause, 
  Heart, 
  Music,
  Plus,
  Search,
  RefreshCw,
  AlertCircle,
  GripVertical,
  Trash2,
  ListMusic
} from 'lucide-vue-next'
import { apiGet, apiPost, apiDelete } from '../api'
import LoadingSpinner from './LoadingSpinner.vue'
import EmptyState from './EmptyState.vue'
import { isFavoriteSong, toggleFavoriteSong } from '../utils/favorites'

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
const isDragging = ref(false)
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
    const next = await apiGet<Track[]>('/queue')
    applyQueueUpdate(markQueueFavorites(next))
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  } finally {
    loading.value = false
  }
}

function markQueueFavorites(list: Track[]): Track[] {
  return list.map((t) => ({
    ...t,
    isLiked: isFavoriteSong(t.id),
  }))
}

function applyQueueUpdate(next: Track[]) {
  const cur = tracks.value
  if (cur.length === next.length) {
    let same = true
    for (let i = 0; i < cur.length; i++) {
      if (cur[i]?.id !== next[i]?.id) {
        same = false
        break
      }
    }
    if (same) {
      for (let i = 0; i < cur.length; i++) {
        Object.assign(cur[i], next[i])
      }
      return
    }
  }
  tracks.value = next
}

async function refreshTracksSilently() {
  try {
    const next = await apiGet<Track[]>('/queue')
    applyQueueUpdate(markQueueFavorites(next))
  } catch {
    // ignore
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

// Remove track from queue
async function removeTrack(trackId: number) {
  try {
    await apiDelete(`/queue/${trackId}`)
    tracks.value = tracks.value.filter(t => t.id !== trackId)
    if (selectedTracks.value.has(trackId)) {
        selectedTracks.value.delete(trackId)
    }
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function deleteSelected() {
  const ids = Array.from(selectedTracks.value)
  if (!ids.length) return
  try {
    // Optimistic UI update
    const previousTracks = [...tracks.value]
    tracks.value = tracks.value.filter(t => !selectedTracks.value.has(t.id))
    selectedTracks.value.clear()
    
    await Promise.all(ids.map(id => apiDelete(`/queue/${id}`)))
  } catch (e: any) {
    error.value = String(e?.message ?? e)
    // Revert if failed (optional, simplified here)
    void loadTracks()
  }
}

// Toggle track like status
async function toggleLike(track: Track) {
  const liked = toggleFavoriteSong({
    id: track.id,
    name: track.title,
    ar: [{ name: track.artist }],
    al: {
      name: track.album,
      picUrl: track.artwork,
    },
    duration: track.duration ? Number(track.duration) * 1000 : undefined,
  })
  track.isLiked = liked
}

// Handle drag end - reorder tracks
function onDragStart() {
  isDragging.value = true
}

function onDragEnd() {
  isDragging.value = false
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

onMounted(() => {
    void loadTracks()
    refreshTimer = window.setInterval(() => {
        if (isDragging.value) return
        void refreshTracksSilently()
    }, 5000)
})

onUnmounted(() => {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
@keyframes music-bar {
  0%, 100% { height: 20%; }
  50% { height: 80%; }
}

.animate-music-bar-1 {
  animation: music-bar 0.8s ease-in-out infinite;
}
.animate-music-bar-2 {
  animation: music-bar 0.8s ease-in-out infinite 0.2s;
}
.animate-music-bar-3 {
  animation: music-bar 0.8s ease-in-out infinite 0.4s;
}

.animate-fade-in {
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-5px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
