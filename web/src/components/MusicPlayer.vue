<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { 
  Play, 
  Pause, 
  SkipBack, 
  SkipForward, 
  Volume2, 
  VolumeX, 
  Repeat, 
  Shuffle,
  Heart,
  MoreHorizontal,
  Maximize2
} from 'lucide-vue-next'
import { apiGet, apiPost, apiPut } from '../api'

const router = useRouter()

interface Track {
  id: number
  title: string
  artist: string
  album?: string
  duration?: number
  artwork?: string
}

function openLyrics() {
  void router.push('/lyrics')
}

interface PlayerState {
  isPlaying: boolean
  currentTime: number
  duration: number
  volume: number
  isMuted: boolean
  isShuffled: boolean
  repeatMode: 'none' | 'one' | 'all'
}

const currentTrack = ref<Track | null>(null)
const playerState = ref<PlayerState>({
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  volume: 100,
  isMuted: false,
  isShuffled: false,
  repeatMode: 'none'
})

const error = ref('')
const isLiked = ref(false)

// Computed properties
const formattedCurrentTime = computed(() => formatTime(playerState.value.currentTime))
const formattedDuration = computed(() => formatTime(playerState.value.duration))
const progressPercent = computed(() => {
  if (playerState.value.duration === 0) return 0
  return (playerState.value.currentTime / playerState.value.duration) * 100
})

// Format time in MM:SS format
function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

// Player controls
async function togglePlayPause() {
  try {
    if (playerState.value.isPlaying) {
      await apiPost('/voice/pause', {})
    } else {
      await apiPost('/voice/play', {})
    }
    await loadPlayerState()
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function skipForward() {
  try {
    await apiPost('/voice/next', {})
    await loadPlayerState()
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function skipBackward() {
  try {
    await apiPost('/voice/previous', {})
    await loadPlayerState()
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function setVolume(volume: number) {
  try {
    playerState.value.volume = volume
    await apiPut('/voice/volume', { volume_percent: volume })
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function toggleMute() {
  try {
    const newVolume = playerState.value.isMuted ? playerState.value.volume : 0
    playerState.value.isMuted = !playerState.value.isMuted
    await apiPut('/voice/volume', { volume_percent: newVolume })
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function seekTo(percent: number) {
  try {
    const seekTime = (percent / 100) * playerState.value.duration
    await apiPost('/voice/seek', { time: seekTime })
    playerState.value.currentTime = seekTime
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

async function toggleLike() {
  if (!currentTrack.value) return
  try {
    if (isLiked.value) {
      await apiPost(`/likes/${currentTrack.value.id}/remove`, {})
    } else {
      await apiPost(`/likes/${currentTrack.value.id}/add`, {})
    }
    isLiked.value = !isLiked.value
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

// Load current player state
async function loadPlayerState() {
  try {
    const state = await apiGet<any>('/voice/status')
    
    playerState.value.isPlaying = state.state === 'playing'
    playerState.value.volume = Number(state.volume_percent ?? 100)
    playerState.value.currentTime = Number(state.current_time ?? 0)
    playerState.value.duration = Number(state.duration ?? 0)
    
    if (state.now_playing_title) {
      currentTrack.value = {
        id: state.track_id || 0,
        title: state.now_playing_title,
        artist: state.now_playing_artist || 'Unknown Artist',
        album: state.now_playing_album,
        artwork: state.artwork_url
      }
    }
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

// Progress bar click handler
function handleProgressClick(event: MouseEvent) {
  const progressBar = event.currentTarget as HTMLElement
  const rect = progressBar.getBoundingClientRect()
  const percent = ((event.clientX - rect.left) / rect.width) * 100
  seekTo(percent)
}

onMounted(() => {
  loadPlayerState()
  // Update player state every second
  setInterval(loadPlayerState, 1000)
})
</script>

<template>
  <div class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-50">
    <div class="max-w-screen-xl mx-auto px-4 py-3">
      <!-- Error display -->
      <div v-if="error" class="mb-2 p-2 bg-red-100 text-red-700 rounded text-sm">
        {{ error }}
      </div>
      
      <!-- Main player content -->
      <div class="flex items-center justify-between gap-4">
        <!-- Track info -->
        <div class="flex items-center gap-3 min-w-0 flex-1">
          <button
            @click="openLyrics"
            class="relative w-12 h-12 bg-gray-200 rounded-lg flex-shrink-0 overflow-hidden group"
            title="查看歌词"
          >
            <img 
              v-if="currentTrack?.artwork" 
              :src="currentTrack.artwork" 
              :alt="currentTrack.title"
              class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
            />
            <div v-else class="w-full h-full bg-gradient-to-br from-blue-400 to-purple-500"></div>
            <div class="absolute inset-0 bg-black/25 opacity-0 group-hover:opacity-100 transition-opacity"></div>
            <div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
              <div class="flex items-center gap-1 text-white text-xs font-medium bg-black/35 px-2 py-1 rounded-full">
                <Maximize2 :size="14" />
                歌词
              </div>
            </div>
          </button>
          
          <div class="min-w-0 flex-1">
            <div class="font-medium text-gray-900 truncate">
              {{ currentTrack?.title || 'No track playing' }}
            </div>
            <div class="text-sm text-gray-500 truncate">
              {{ currentTrack?.artist || '' }}
            </div>
          </div>
          
          <button 
            @click="toggleLike"
            :class="[
              'p-2 rounded-full transition-colors',
              isLiked ? 'text-red-500 hover:text-red-600' : 'text-gray-400 hover:text-gray-600'
            ]"
          >
            <Heart :size="20" :fill="isLiked ? 'currentColor' : 'none'" />
          </button>
        </div>
        
        <!-- Player controls -->
        <div class="flex flex-col items-center gap-2 flex-1 max-w-md">
          <!-- Control buttons -->
          <div class="flex items-center gap-2">
            <button class="p-2 text-gray-600 hover:text-gray-900 transition-colors">
              <Shuffle :size="18" />
            </button>
            
            <button 
              @click="skipBackward"
              class="p-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <SkipBack :size="20" />
            </button>
            
            <button 
              @click="togglePlayPause"
              class="p-3 bg-blue-600 hover:bg-blue-700 text-white rounded-full transition-colors"
            >
              <Play v-if="!playerState.isPlaying" :size="20" />
              <Pause v-else :size="20" />
            </button>
            
            <button 
              @click="skipForward"
              class="p-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <SkipForward :size="20" />
            </button>
            
            <button class="p-2 text-gray-600 hover:text-gray-900 transition-colors">
              <Repeat :size="18" />
            </button>
          </div>
          
          <!-- Progress bar -->
          <div class="flex items-center gap-2 w-full">
            <span class="text-xs text-gray-500 min-w-[35px]">{{ formattedCurrentTime }}</span>
            
            <div 
              class="flex-1 h-1 bg-gray-200 rounded-full cursor-pointer relative group"
              @click="handleProgressClick"
            >
              <div 
                class="h-full bg-blue-600 rounded-full transition-all duration-200"
                :style="{ width: `${progressPercent}%` }"
              ></div>
              <div 
                class="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-blue-600 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                :style="{ left: `${progressPercent}%`, transform: 'translateX(-50%) translateY(-50%)' }"
              ></div>
            </div>
            
            <span class="text-xs text-gray-500 min-w-[35px]">{{ formattedDuration }}</span>
          </div>
        </div>
        
        <!-- Volume and additional controls -->
        <div class="flex items-center gap-2 flex-1 justify-end">
          <button 
            @click="toggleMute"
            class="p-2 text-gray-600 hover:text-gray-900 transition-colors"
          >
            <VolumeX v-if="playerState.isMuted" :size="20" />
            <Volume2 v-else :size="20" />
          </button>
          
          <div class="w-20">
            <input
              type="range"
              min="0"
              max="100"
              :value="playerState.volume"
              @input="setVolume(($event.target as HTMLInputElement).valueAsNumber)"
              class="w-full h-1 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
            />
          </div>
          
          <button class="p-2 text-gray-600 hover:text-gray-900 transition-colors">
            <MoreHorizontal :size="20" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.slider::-webkit-slider-thumb {
  appearance: none;
  height: 12px;
  width: 12px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
}

.slider::-moz-range-thumb {
  height: 12px;
  width: 12px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
  border: none;
}
</style>
