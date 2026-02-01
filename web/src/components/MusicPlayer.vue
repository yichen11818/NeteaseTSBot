<template>
  <div class="fixed bottom-0 left-0 right-0 bg-white/90 backdrop-blur-lg border-t border-gray-200 shadow-[0_-4px_20px_rgba(0,0,0,0.05)] z-50 transition-all duration-300">
    <!-- Progress Bar (Floating on top or integrated) -->
    <div 
      class="absolute top-0 left-0 right-0 h-1 bg-transparent group cursor-pointer"
      @click="handleProgressClick"
    >
      <div class="absolute inset-0 bg-gray-200/50 group-hover:h-2 transition-all duration-200"></div>
      <div 
        class="absolute top-0 left-0 h-full bg-blue-600 group-hover:h-2 transition-all duration-200"
        :style="{ width: `${progressPercent}%` }"
      >
        <div class="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white border border-gray-200 rounded-full shadow-md opacity-0 group-hover:opacity-100 transition-opacity transform translate-x-1/2 scale-0 group-hover:scale-100"></div>
      </div>
    </div>

    <div class="max-w-screen-2xl mx-auto px-4 sm:px-6 py-3">
      <!-- Error display -->
      <div v-if="error" class="absolute bottom-full left-1/2 -translate-x-1/2 mb-4 px-4 py-2 bg-red-500 text-white rounded-lg text-sm shadow-lg animate-fade-in-up">
        {{ error }}
      </div>
      
      <!-- Main player content -->
      <div class="flex items-center justify-between gap-2 sm:gap-4 h-14">
        <!-- Track info -->
        <div class="flex items-center gap-3 min-w-0 flex-1 sm:w-[30%] sm:flex-none">
          <button
            @click="openLyrics"
            class="relative w-10 h-10 sm:w-12 sm:h-12 rounded-lg flex-shrink-0 overflow-hidden group shadow-sm ring-1 ring-black/5"
            title="查看歌词"
          >
            <img 
              v-if="currentTrack?.artwork" 
              :src="currentTrack.artwork" 
              :alt="currentTrack.title"
              class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
            />
            <div v-else class="w-full h-full bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center">
              <div class="text-white/50">🎵</div>
            </div>
            
            <!-- Hover overlay -->
            <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center backdrop-blur-[1px]">
              <Maximize2 :size="16" class="text-white drop-shadow-md" />
            </div>
          </button>
          
          <div class="min-w-0 flex-1 flex flex-col justify-center">
            <div class="font-semibold text-gray-900 truncate text-sm leading-tight hover:underline cursor-pointer" @click="openLyrics">
              {{ currentTrack?.title || '未播放' }}
            </div>
            <div class="text-xs text-gray-500 truncate mt-0.5">
              {{ currentTrack?.artist || 'Ready to play' }}
            </div>
          </div>
          
          <button 
            @click="toggleLike"
            :class="[
              'p-2 rounded-full transition-all duration-200 hidden sm:block',
              isLiked 
                ? 'text-red-500 hover:bg-red-50' 
                : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
            ]"
            :disabled="!currentTrack"
          >
            <Heart :size="18" :fill="isLiked ? 'currentColor' : 'none'" />
          </button>
        </div>
        
        <!-- Player controls (Center) -->
        <div class="flex flex-col items-center justify-center gap-1 flex-none sm:flex-1 max-w-md">
          <div class="flex items-center gap-2 sm:gap-4">
            <button 
              @click="toggleShuffle"
              :class="[
                'p-2 transition-colors hidden sm:block rounded-full',
                playerState.isShuffled 
                  ? 'text-blue-600 bg-blue-50 hover:bg-blue-100' 
                  : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100'
              ]"
              title="随机播放"
            >
              <Shuffle :size="18" />
            </button>
            
            <button 
              @click="skipBackward"
              class="p-1.5 sm:p-2 text-gray-700 hover:text-blue-600 transition-colors hover:bg-gray-100 rounded-full"
            >
              <SkipBack :size="20" class="sm:w-[22px] sm:h-[22px]" fill="currentColor" />
            </button>
            
            <button 
              @click="togglePlayPause"
              class="p-2 sm:p-3 bg-gray-900 hover:bg-gray-800 text-white rounded-full transition-all duration-200 shadow-md hover:shadow-lg hover:scale-105 active:scale-95 flex items-center justify-center w-10 h-10 sm:w-12 sm:h-12"
            >
              <Play v-if="!playerState.isPlaying" :size="18" class="sm:w-5 sm:h-5 ml-0.5" fill="currentColor" />
              <Pause v-else :size="18" class="sm:w-5 sm:h-5" fill="currentColor" />
            </button>
            
            <button 
              @click="skipForward"
              class="p-1.5 sm:p-2 text-gray-700 hover:text-blue-600 transition-colors hover:bg-gray-100 rounded-full"
            >
              <SkipForward :size="20" class="sm:w-[22px] sm:h-[22px]" fill="currentColor" />
            </button>
            
            <button 
              @click="toggleRepeat"
              :class="[
                'p-2 transition-colors hidden sm:block rounded-full relative',
                playerState.repeatMode !== 'none' 
                  ? 'text-blue-600 bg-blue-50 hover:bg-blue-100' 
                  : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100'
              ]"
              :title="getRepeatTitle()"
            >
              <Repeat :size="18" />
              <span 
                v-if="playerState.repeatMode === 'one'"
                class="absolute -top-0.5 -right-0.5 w-3 h-3 bg-blue-600 text-white text-xs rounded-full flex items-center justify-center font-bold"
                style="font-size: 8px; line-height: 1;"
              >
                1
              </span>
            </button>
          </div>
          
          <!-- Time info (Mobile hidden, shown on Desktop below controls if needed, but here we keep it simple) -->
        </div>
        
        <!-- Volume and additional controls (Right) -->
        <div class="flex items-center gap-3 justify-end w-auto sm:w-[30%] min-w-0 relative">
          <span class="text-xs text-gray-400 font-mono hidden lg:block w-20 text-right">
            {{ formattedCurrentTime }} / {{ formattedDuration }}
          </span>

          <div class="flex items-center gap-2 group/volume hidden sm:flex">
            <button 
              @click="toggleMute"
              class="p-1.5 text-gray-500 hover:text-gray-800 transition-colors"
            >
              <VolumeX v-if="playerState.isMuted || playerState.volume === 0" :size="20" />
              <Volume2 v-else :size="20" />
            </button>
            
            <div class="w-24 h-1.5 bg-gray-200 rounded-full relative cursor-pointer hidden md:block overflow-hidden">
              <div 
                class="absolute inset-0 bg-gray-200"
                @click="(e) => setVolumeByClick(e)"
              ></div>
              <div 
                class="absolute top-0 left-0 h-full bg-gray-500 hover:bg-gray-700 transition-colors"
                :style="{ width: `${playerState.volume}%` }"
                @click="(e) => setVolumeByClick(e)"
              ></div>
              <!-- Hidden Range Input for functionality -->
              <input
                type="range"
                min="0"
                max="100"
                :value="playerState.volume"
                @input="setVolume(($event.target as HTMLInputElement).valueAsNumber)"
                class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
            </div>
          </div>
          
          <button
            class="p-2 text-gray-500 hover:text-gray-900 transition-colors border-l border-gray-200 pl-4 ml-1 hidden sm:block"
            @click="toggleFxPanel"
          >
            <MoreHorizontal :size="20" />
          </button>

          <div v-if="showFxPanel" class="absolute bottom-full right-4 mb-3 w-80 bg-white border border-gray-200 rounded-xl shadow-xl p-4">
            <div class="flex items-center justify-between mb-3">
              <div class="text-sm font-semibold text-gray-900">音效</div>
              <button class="p-1 text-gray-400 hover:text-gray-700" @click="showFxPanel = false">✕</button>
            </div>

            <div class="space-y-4">
              <div>
                <div class="flex items-center justify-between text-xs text-gray-600 mb-1">
                  <div>低音 (dB)</div>
                  <div class="font-mono tabular-nums">{{ fxBassDb.toFixed(1) }}</div>
                </div>
                <input
                  type="range"
                  min="0"
                  max="18"
                  step="0.1"
                  :value="fxBassDb"
                  class="w-full"
                  @input="onFxBassDbInput(($event.target as HTMLInputElement).valueAsNumber)"
                />
              </div>

              <div>
                <div class="flex items-center justify-between text-xs text-gray-600 mb-1">
                  <div>混响</div>
                  <div class="font-mono tabular-nums">{{ fxReverbMix.toFixed(2) }}</div>
                </div>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  :value="fxReverbMix"
                  class="w-full"
                  @input="onFxReverbMixInput(($event.target as HTMLInputElement).valueAsNumber)"
                />
              </div>

              <div>
                <div class="flex items-center justify-between text-xs text-gray-600 mb-1">
                  <div>声像 (L/R)</div>
                  <div class="font-mono tabular-nums">{{ fxPan.toFixed(2) }}</div>
                </div>
                <input
                  type="range"
                  min="-1"
                  max="1"
                  step="0.01"
                  :value="fxPan"
                  class="w-full"
                  @input="onFxPanInput(($event.target as HTMLInputElement).valueAsNumber)"
                />
              </div>

              <div>
                <div class="flex items-center justify-between text-xs text-gray-600 mb-1">
                  <div>立体声宽度</div>
                  <div class="font-mono tabular-nums">{{ fxWidth.toFixed(2) }}</div>
                </div>
                <input
                  type="range"
                  min="0"
                  max="3"
                  step="0.01"
                  :value="fxWidth"
                  class="w-full"
                  @input="onFxWidthInput(($event.target as HTMLInputElement).valueAsNumber)"
                />
              </div>

              <label class="flex items-center justify-between text-sm text-gray-700">
                <span>左右互换</span>
                <input type="checkbox" :checked="fxSwapLr" @change="onFxSwapChange(($event.target as HTMLInputElement).checked)" />
              </label>

              <div class="flex items-center justify-end gap-2">
                <button
                  class="px-3 py-1.5 text-sm rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700"
                  @click="resetFx"
                  :disabled="fxLoading"
                >
                  重置
                </button>
                <button
                  class="px-3 py-1.5 text-sm rounded-lg bg-blue-600 hover:bg-blue-700 text-white"
                  @click="reloadFx"
                  :disabled="fxLoading"
                >
                  刷新
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted } from 'vue'
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
import { isFavoriteSong, toggleFavoriteSong } from '../utils/favorites'

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
const queue = ref<Track[]>([])
const currentTrackIndex = ref(-1)
const shuffledQueue = ref<number[]>([])

const showFxPanel = ref(false)
const fxLoading = ref(false)
const fxPan = ref(0)
const fxWidth = ref(1)
const fxSwapLr = ref(false)
const fxBassDb = ref(0)
const fxReverbMix = ref(0)
let fxDebounceTimer: number | null = null
let fxPending: { pan?: number; width?: number; swap_lr?: boolean; bass_db?: number; reverb_mix?: number } = {}
let timer: number | null = null
let pollInterval = 1000 // Dynamic polling interval
let lastUpdateTime = 0

// Computed properties
const formattedCurrentTime = computed(() => formatTime(playerState.value.currentTime))
const formattedDuration = computed(() => formatTime(playerState.value.duration))
const progressPercent = computed(() => {
  if (playerState.value.duration === 0) return 0
  return (playerState.value.currentTime / playerState.value.duration) * 100
})

// Format time in MM:SS format
function formatTime(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
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
    setTimeout(() => error.value = '', 3000)
  }
}

function showError(msg: string) {
  error.value = msg
  setTimeout(() => error.value = '', 3000)
}

function toggleFxPanel() {
  showFxPanel.value = !showFxPanel.value
  if (showFxPanel.value) {
    void loadFx()
  }
}

async function loadFx() {
  fxLoading.value = true
  try {
    const fx = await apiGet<any>('/voice/fx')
    fxPan.value = Number(fx?.pan ?? 0)
    fxWidth.value = Number(fx?.width ?? 1)
    fxSwapLr.value = Boolean(fx?.swap_lr ?? false)
    fxBassDb.value = Number(fx?.bass_db ?? 0)
    fxReverbMix.value = Number(fx?.reverb_mix ?? 0)
  } catch (e: any) {
    showError(String(e?.message ?? e))
  } finally {
    fxLoading.value = false
  }
}

async function pushFx(update: { pan?: number; width?: number; swap_lr?: boolean; bass_db?: number; reverb_mix?: number }) {
  try {
    await apiPut('/voice/fx', update)
  } catch (e: any) {
    showError(String(e?.message ?? e))
  }
}

function scheduleFxUpdate(update: { pan?: number; width?: number; swap_lr?: boolean; bass_db?: number; reverb_mix?: number }) {
  fxPending = { ...fxPending, ...update }
  if (fxDebounceTimer) {
    window.clearTimeout(fxDebounceTimer)
  }
  fxDebounceTimer = window.setTimeout(() => {
    const payload = fxPending
    fxPending = {}
    fxDebounceTimer = null
    void pushFx(payload)
  }, 50)
}

function onFxPanInput(v: number) {
  fxPan.value = v
  scheduleFxUpdate({ pan: v })
}

function onFxWidthInput(v: number) {
  fxWidth.value = v
  scheduleFxUpdate({ width: v })
}

function onFxSwapChange(v: boolean) {
  fxSwapLr.value = v
  scheduleFxUpdate({ swap_lr: v })
}

function onFxBassDbInput(v: number) {
  fxBassDb.value = v
  scheduleFxUpdate({ bass_db: v })
}

function onFxReverbMixInput(v: number) {
  fxReverbMix.value = v
  scheduleFxUpdate({ reverb_mix: v })
}

async function reloadFx() {
  await loadFx()
}

async function resetFx() {
  fxPan.value = 0
  fxWidth.value = 1
  fxSwapLr.value = false
  fxBassDb.value = 0
  fxReverbMix.value = 0
  await pushFx({ pan: 0, width: 1, swap_lr: false, bass_db: 0, reverb_mix: 0 })
}

async function skipForward() {
  try {
    await apiPost('/voice/next', {})
    await loadPlayerState()
  } catch (e: any) {
    error.value = String(e?.message ?? e)
    setTimeout(() => error.value = '', 3000)
  }
}

async function skipBackward() {
  try {
    await apiPost('/voice/previous', {})
    await loadPlayerState()
  } catch (e: any) {
    error.value = String(e?.message ?? e)
    setTimeout(() => error.value = '', 3000)
  }
}

async function setVolume(volume: number) {
  try {
    playerState.value.volume = volume
    await apiPut('/voice/volume', { volume_percent: volume })
  } catch (e: any) {
    // Silent fail for volume slider drag
  }
}

function setVolumeByClick(event: MouseEvent) {
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const percent = ((event.clientX - rect.left) / rect.width) * 100
  setVolume(Math.min(100, Math.max(0, percent)))
}

async function toggleMute() {
  try {
    const newVolume = playerState.value.isMuted ? playerState.value.volume || 50 : 0
    playerState.value.isMuted = !playerState.value.isMuted
    await apiPut('/voice/volume', { volume_percent: newVolume })
  } catch (e: any) {
    error.value = String(e?.message ?? e)
    setTimeout(() => error.value = '', 3000)
  }
}

async function seekTo(percent: number) {
  try {
    const seekTime = (percent / 100) * playerState.value.duration
    await apiPost('/voice/seek', { time: seekTime })
    playerState.value.currentTime = seekTime
  } catch (e: any) {
    error.value = String(e?.message ?? e)
    setTimeout(() => error.value = '', 3000)
  }
}

async function toggleShuffle() {
  try {
    playerState.value.isShuffled = !playerState.value.isShuffled
    if (playerState.value.isShuffled) {
      generateShuffledQueue()
    }
    await apiPost('/voice/shuffle', { enabled: playerState.value.isShuffled })
  } catch (e: any) {
    error.value = String(e?.message ?? e)
    setTimeout(() => error.value = '', 3000)
  }
}

async function toggleRepeat() {
  try {
    const modes: ('none' | 'one' | 'all')[] = ['none', 'all', 'one']
    const currentIndex = modes.indexOf(playerState.value.repeatMode)
    playerState.value.repeatMode = modes[(currentIndex + 1) % modes.length]
    await apiPost('/voice/repeat', { mode: playerState.value.repeatMode })
  } catch (e: any) {
    error.value = String(e?.message ?? e)
    setTimeout(() => error.value = '', 3000)
  }
}

function getRepeatTitle(): string {
  switch (playerState.value.repeatMode) {
    case 'none': return '循环播放：关闭'
    case 'all': return '循环播放：列表循环'
    case 'one': return '循环播放：单曲循环'
    default: return '循环播放'
  }
}

function generateShuffledQueue() {
  if (queue.value.length === 0) return
  
  const indices = Array.from({ length: queue.value.length }, (_, i) => i)
  
  // Fisher-Yates shuffle algorithm
  for (let i = indices.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[indices[i], indices[j]] = [indices[j], indices[i]]
  }
  
  shuffledQueue.value = indices
}



async function loadQueue() {
  try {
    queue.value = await apiGet<Track[]>('/queue')
    if (currentTrack.value) {
      currentTrackIndex.value = queue.value.findIndex(t => t.id === currentTrack.value?.id)
    }
  } catch (e: any) {
    // Silent fail for queue loading
  }
}

async function toggleLike() {
  if (!currentTrack.value) return
  const liked = toggleFavoriteSong({
    id: currentTrack.value.id,
    name: currentTrack.value.title,
    ar: [{ name: currentTrack.value.artist }],
    al: {
      name: currentTrack.value.album,
      picUrl: currentTrack.value.artwork,
    },
  })
  isLiked.value = liked
}

// Load current player state with adaptive polling
async function loadPlayerState() {
  try {
    const state = await apiGet<any>('/voice/status')
    
    const wasPlaying = playerState.value.isPlaying
    const previousTrackId = currentTrack.value?.id
    
    playerState.value.isPlaying = state.state === 'playing'
    playerState.value.volume = Number(state.volume_percent ?? 100)
    playerState.value.currentTime = Number(state.current_time ?? 0)
    playerState.value.duration = Number(state.duration ?? 0)
    playerState.value.isShuffled = Boolean(state.is_shuffled ?? false)
    playerState.value.repeatMode = state.repeat_mode ?? 'none'
    
    // Check if track changed to update local like status
    const nextTrackId = Number(state.track_id || 0)
    if (nextTrackId && nextTrackId !== currentTrack.value?.id) {
      isLiked.value = isFavoriteSong(nextTrackId)

      // Update current track index when track changes
      if (queue.value.length > 0) {
        currentTrackIndex.value = queue.value.findIndex(t => t.id === nextTrackId)
      }
    }

    if (state.now_playing_title) {
      currentTrack.value = {
        id: state.track_id || 0,
        title: state.now_playing_title,
        artist: state.now_playing_artist || 'Unknown Artist',
        album: state.now_playing_album,
        artwork: state.artwork_url
      }

      isLiked.value = isFavoriteSong(Number(currentTrack.value.id || 0))
    }
    
    // Handle track end and repeat logic
    if (state.state === 'ended' || (state.state === 'stopped' && playerState.value.currentTime >= playerState.value.duration && playerState.value.duration > 0)) {
      await handleTrackEnd()
    }
    
    // Adaptive polling logic
    updatePollInterval(wasPlaying, previousTrackId, state)
    
  } catch (e: any) {
    // Don't show error for status poll
    // Increase poll interval on error to reduce load
    pollInterval = Math.min(pollInterval * 1.5, 5000)
  }
}

function updatePollInterval(wasPlaying: boolean, previousTrackId: number | undefined, state: any) {
  const now = Date.now()
  const isPlaying = state.state === 'playing'
  const trackChanged = state.track_id !== previousTrackId
  
  // Fast polling when playing or track just changed
  if (isPlaying || trackChanged || (wasPlaying !== isPlaying)) {
    pollInterval = 1000
  }
  // Slower polling when paused/idle for more than 30 seconds
  else if (!isPlaying && (now - lastUpdateTime > 30000)) {
    pollInterval = 3000
  }
  // Medium polling when recently paused
  else if (!isPlaying) {
    pollInterval = 2000
  }
  
  lastUpdateTime = now
  
  // Restart timer with new interval if it changed
  if (timer) {
    clearInterval(timer)
    timer = window.setInterval(() => {
      void loadPlayerState()
    }, pollInterval)
  }
}

async function handleTrackEnd() {
  try {
    if (playerState.value.repeatMode === 'one') {
      // Repeat current track
      await apiPost('/voice/seek', { time: 0 })
      await apiPost('/voice/play', {})
    } else if (playerState.value.repeatMode === 'all' || currentTrackIndex.value < queue.value.length - 1) {
      // Play next track or loop to beginning
      await skipForward()
    }
    // If repeatMode is 'none' and we're at the end, just stop
  } catch (e: any) {
    error.value = String(e?.message ?? e)
    setTimeout(() => error.value = '', 3000)
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
  void loadPlayerState()
  void loadQueue()
  timer = window.setInterval(() => {
    void loadPlayerState()
  }, pollInterval)
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  if (fxDebounceTimer) {
    window.clearTimeout(fxDebounceTimer)
    fxDebounceTimer = null
  }
})
</script>

<style scoped>
@keyframes fade-in-up {
  from { opacity: 0; transform: translate(-50%, 10px); }
  to { opacity: 1; transform: translate(-50%, 0); }
}
.animate-fade-in-up {
  animation: fade-in-up 0.3s ease-out forwards;
}
</style>
