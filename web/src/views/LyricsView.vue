<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { apiGet, apiPost } from '../api'
import LyricsDisplay from '../components/LyricsDisplay.vue'
import { isFavoriteSong, toggleFavoriteSong } from '../utils/favorites'
import { 
  ArrowLeft, 
  Play, 
  Pause, 
  SkipBack, 
  SkipForward,
  Heart,
  MoreHorizontal,
  Shuffle,
  Repeat
} from 'lucide-vue-next'

const router = useRouter()

const trackId = ref<number>(0)
const currentTime = ref<number>(0)
const duration = ref<number>(0)
const artwork = ref<string>('')
const title = ref<string>('')
const artist = ref<string>('')
const album = ref<string>('')
const isPlaying = ref<boolean>(false)
const isLiked = ref<boolean>(false)
const isShuffled = ref<boolean>(false)
const repeatMode = ref<'none' | 'one' | 'all'>('none')

let timer: number | null = null

async function loadState() {
  try {
    const st = await apiGet<any>('/voice/status')
    trackId.value = Number(st?.track_id ?? 0)
    currentTime.value = Number(st?.current_time ?? 0)
    duration.value = Number(st?.duration ?? 0)
    artwork.value = String(st?.artwork_url || '')
    title.value = String(st?.now_playing_title || '')
    artist.value = String(st?.now_playing_artist || '')
    album.value = String(st?.now_playing_album || '')
    isPlaying.value = st?.state === 'playing'
    isShuffled.value = Boolean(st?.is_shuffled ?? false)
    repeatMode.value = st?.repeat_mode ?? 'none'
    isLiked.value = isFavoriteSong(trackId.value)
  } catch {
    // ignore
  }
}

const backdropStyle = computed(() => {
  if (!artwork.value) {
    return {
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
    }
  }
  return {
    backgroundImage: `url(${artwork.value})`,
  }
})

const progressPercent = computed(() => {
  if (!duration.value) return 0
  return (currentTime.value / duration.value) * 100
})

function formatTime(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function goBack() {
  router.back()
}

async function togglePlayPause() {
  try {
    if (isPlaying.value) {
      await apiPost('/voice/pause', {})
    } else {
      await apiPost('/voice/play', {})
    }
    await loadState()
  } catch (e) {
    console.error('Failed to toggle playback:', e)
  }
}

async function skipForward() {
  try {
    await apiPost('/voice/next', {})
    await loadState()
  } catch (e) {
    console.error('Failed to skip forward:', e)
  }
}

async function skipBackward() {
  try {
    await apiPost('/voice/previous', {})
    await loadState()
  } catch (e) {
    console.error('Failed to skip backward:', e)
  }
}

async function seekTo(event: MouseEvent) {
  try {
    const target = event.currentTarget as HTMLElement
    const rect = target.getBoundingClientRect()
    const percent = ((event.clientX - rect.left) / rect.width)
    const seekTime = percent * duration.value
    await apiPost('/voice/seek', { time: seekTime })
    currentTime.value = seekTime
  } catch (e) {
    console.error('Failed to seek:', e)
  }
}

async function toggleLike() {
  if (!trackId.value) return
  const liked = toggleFavoriteSong({
    id: trackId.value,
    name: title.value,
    ar: [{ name: artist.value }],
    al: {
      name: album.value,
      picUrl: artwork.value,
    },
  })
  isLiked.value = liked
}

async function toggleShuffle() {
  try {
    isShuffled.value = !isShuffled.value
    await apiPost('/voice/shuffle', { enabled: isShuffled.value })
    await loadState()
  } catch (e) {
    console.error('Failed to toggle shuffle:', e)
  }
}

async function toggleRepeat() {
  try {
    const modes: ('none' | 'one' | 'all')[] = ['none', 'all', 'one']
    const currentIndex = modes.indexOf(repeatMode.value)
    repeatMode.value = modes[(currentIndex + 1) % modes.length]
    await apiPost('/voice/repeat', { mode: repeatMode.value })
    await loadState()
  } catch (e) {
    console.error('Failed to toggle repeat:', e)
  }
}

onMounted(() => {
  void loadState()
  timer = window.setInterval(() => {
    void loadState()
  }, 1000)
})

onUnmounted(() => {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
})

</script>

<template>
  <div class="relative h-full w-full overflow-hidden bg-black">
    <!-- Dynamic fluid background (Simulated Color Extraction) -->
    <div 
      class="absolute inset-0 bg-cover bg-center transition-all duration-1000 ease-in-out transform scale-110 filter blur-[100px] opacity-60" 
      :style="backdropStyle"
    ></div>
    
    <!-- Gradient Overlay: Shows color at top, fades to solid black at bottom -->
    <div class="absolute inset-0 bg-gradient-to-b from-black/10 via-black/40 to-black"></div>
    
    <!-- Animated background particles (subtle) -->
    <div class="absolute inset-0 overflow-hidden opacity-30 pointer-events-none">
      <div class="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-primary-500/20 rounded-full blur-[100px] animate-pulse"></div>
      <div class="absolute bottom-1/3 right-1/3 w-[400px] h-[400px] bg-purple-500/20 rounded-full blur-[100px] animate-pulse" style="animation-delay: 2s;"></div>
    </div>

    <div class="relative h-full flex flex-col z-10">
      <!-- Minimal header -->
      <header class="flex-shrink-0 flex items-center justify-between px-6 py-6 md:px-10 md:py-8">
        <button
          @click="goBack"
          class="p-3 rounded-full bg-white/10 backdrop-blur-md text-white/90 hover:bg-white/20 hover:text-white transition-all duration-300 group"
        >
          <ArrowLeft :size="20" class="group-hover:-translate-x-0.5 transition-transform" />
        </button>
        
        <!-- Track Info (Mobile Only - Small) -->
        <div class="md:hidden flex flex-col items-center flex-1 mx-4 opacity-80">
          <div class="text-white text-xs font-semibold tracking-wider uppercase">Now Playing</div>
        </div>
        
        <div class="w-10 md:hidden"></div> <!-- Spacer -->
      </header>

      <!-- Main content -->
      <div class="flex-1 min-h-0 w-full max-w-7xl mx-auto px-4 md:px-10 pb-4 md:pb-8 flex flex-col md:flex-row gap-4 md:gap-16 items-center md:items-start justify-center">
        
        <!-- Left Side: Album Art & Info (Desktop) -->
        <div class="hidden md:flex flex-col gap-8 w-full max-w-sm lg:max-w-md sticky top-24 h-full max-h-[calc(100vh-8rem)]">
          <!-- Album Artwork -->
          <div class="relative aspect-square w-full rounded-2xl shadow-2xl overflow-hidden ring-1 ring-white/10 flex-shrink-0">
            <img 
              v-if="artwork" 
              :src="artwork" 
              :alt="title" 
              class="w-full h-full object-cover transition-transform duration-700 hover:scale-105" 
            />
            <div v-else class="w-full h-full bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center">
              <div class="text-white/20 text-6xl">🎵</div>
            </div>
          </div>
          
          <!-- Track Details -->
          <div class="space-y-2 flex-shrink-0">
            <h1 class="text-3xl lg:text-4xl font-bold text-white tracking-tight leading-tight line-clamp-2">
              {{ title || '暂无播放' }}
            </h1>
            <div class="text-xl text-white/60 font-medium line-clamp-1">
              {{ artist }}
            </div>
            <div class="text-white/40 text-sm font-medium line-clamp-1">
              {{ album }}
            </div>
          </div>
          
          <!-- Desktop Controls -->
          <div class="flex-1"></div> <!-- Spacer to push controls down -->
          
          <!-- Integrated Player Controls -->
          <div class="bg-white/10 backdrop-blur-md rounded-2xl p-6 border border-white/5 shadow-xl">
            <!-- Progress Bar -->
            <div class="flex items-center gap-3 text-xs text-white/50 font-mono mb-4">
              <span class="w-10 text-right">{{ formatTime(currentTime) }}</span>
              <div 
                class="flex-1 h-1 bg-white/10 rounded-full cursor-pointer relative group"
                @click="seekTo"
              >
                <div 
                  class="absolute top-0 left-0 h-full bg-white rounded-full opacity-80 group-hover:opacity-100 transition-all"
                  :style="{ width: `${progressPercent}%` }"
                ></div>
                <div 
                  class="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full shadow-lg opacity-0 group-hover:opacity-100 transition-opacity"
                  :style="{ left: `${progressPercent}%`, transform: 'translate(-50%, -50%)' }"
                ></div>
              </div>
              <span class="w-10">{{ formatTime(duration) }}</span>
            </div>

            <!-- Buttons -->
            <div class="flex items-center justify-between">
              <button 
                @click="toggleShuffle"
                :class="[
                  'p-2 transition-colors rounded-full hover:bg-white/10 active:scale-95',
                  isShuffled ? 'text-blue-400 bg-white/10' : 'text-white/40 hover:text-white'
                ]"
                title="随机播放"
              >
                <Shuffle :size="20" />
              </button>
              
              <div class="flex items-center gap-6">
                <button 
                  @click="skipBackward"
                  class="text-white/70 hover:text-white transition-colors p-2 hover:scale-110 active:scale-95 transform duration-200"
                >
                  <SkipBack :size="28" fill="currentColor" />
                </button>
                
                <button 
                  @click="togglePlayPause"
                  class="bg-white text-black rounded-full p-4 hover:scale-105 active:scale-95 transition-all shadow-lg"
                >
                  <Play v-if="!isPlaying" :size="28" fill="currentColor" class="ml-1" />
                  <Pause v-else :size="28" fill="currentColor" />
                </button>
                
                <button 
                  @click="skipForward"
                  class="text-white/70 hover:text-white transition-colors p-2 hover:scale-110 active:scale-95 transform duration-200"
                >
                  <SkipForward :size="28" fill="currentColor" />
                </button>
              </div>
              
              <div class="flex items-center gap-2">
                <button 
                  @click="toggleRepeat"
                  :class="[
                    'p-2 transition-colors rounded-full relative hover:bg-white/10 active:scale-95',
                    repeatMode !== 'none' ? 'text-blue-400 bg-white/10' : 'text-white/40 hover:text-white'
                  ]"
                  title="循环播放"
                >
                  <Repeat :size="20" />
                  <span 
                    v-if="repeatMode === 'one'"
                    class="absolute top-1 right-1 w-2.5 h-2.5 bg-blue-500 text-white text-[8px] rounded-full flex items-center justify-center font-bold"
                  >1</span>
                </button>

                <button 
                  @click="toggleLike"
                  :class="[
                    'p-2 transition-colors active:scale-95',
                    isLiked ? 'text-red-500' : 'text-white/40 hover:text-white'
                  ]"
                  title="收藏"
                >
                  <Heart :size="20" :fill="isLiked ? 'currentColor' : 'none'" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Right Side: Lyrics -->
        <div class="flex-1 h-full w-full max-w-5xl relative flex flex-col">
          <LyricsDisplay
            :key="trackId"
            :track-id="trackId"
            :current-time="currentTime"
            :is-visible="true"
            :show-header="false"
            theme="apple-music"
            class="flex-1 mask-gradient pb-32 md:pb-0"
          />
          
          <!-- Mobile Player Controls (Fixed Bottom) -->
          <div class="md:hidden fixed bottom-0 left-0 right-0 p-4 pb-[calc(env(safe-area-inset-bottom)+1rem)] z-50 bg-gradient-to-t from-black via-black/80 to-transparent">
            <div class="bg-white/10 backdrop-blur-xl rounded-2xl p-4 border border-white/5 shadow-2xl">
              <!-- Mobile Track Info -->
              <div class="flex items-center justify-between mb-4">
                <div class="min-w-0 flex-1">
                  <div class="text-white font-bold truncate text-lg">{{ title }}</div>
                  <div class="text-white/60 text-sm truncate">{{ artist }}</div>
                </div>
                <button 
                  @click="toggleLike"
                  :class="[
                    'p-2 transition-colors',
                    isLiked ? 'text-red-500' : 'text-white/40 hover:text-white'
                  ]"
                >
                  <Heart :size="24" :fill="isLiked ? 'currentColor' : 'none'" />
                </button>
              </div>

              <!-- Mobile Progress -->
              <div 
                class="h-1 bg-white/10 rounded-full cursor-pointer relative mb-4"
                @click="seekTo"
              >
                <div 
                  class="absolute top-0 left-0 h-full bg-white rounded-full"
                  :style="{ width: `${progressPercent}%` }"
                ></div>
              </div>

              <!-- Mobile Buttons -->
              <div class="flex items-center justify-around">
                <button 
                  @click="toggleShuffle"
                  :class="[
                    'p-2 transition-colors rounded-full active:scale-95',
                    isShuffled ? 'text-blue-400 bg-white/10' : 'text-white/40 hover:text-white'
                  ]"
                >
                  <Shuffle :size="20" />
                </button>
                <button @click="skipBackward" class="text-white/80 p-2 active:scale-95 transition-transform">
                  <SkipBack :size="24" fill="currentColor" />
                </button>
                <button 
                  @click="togglePlayPause"
                  class="bg-white text-black rounded-full p-3 shadow-lg active:scale-95 transition-transform"
                >
                  <Play v-if="!isPlaying" :size="24" fill="currentColor" class="ml-0.5" />
                  <Pause v-else :size="24" fill="currentColor" />
                </button>
                <button @click="skipForward" class="text-white/80 p-2 active:scale-95 transition-transform">
                  <SkipForward :size="24" fill="currentColor" />
                </button>
                <button 
                  @click="toggleRepeat"
                  :class="[
                    'p-2 transition-colors rounded-full relative active:scale-95',
                    repeatMode !== 'none' ? 'text-blue-400 bg-white/10' : 'text-white/40 hover:text-white'
                  ]"
                >
                  <Repeat :size="20" />
                  <span 
                    v-if="repeatMode === 'one'"
                    class="absolute top-1 right-1 w-2.5 h-2.5 bg-blue-500 text-white text-[8px] rounded-full flex items-center justify-center font-bold"
                  >1</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mask-gradient {
  mask-image: linear-gradient(to bottom, 
    transparent 0%, 
    black 10%, 
    black 80%, 
    transparent 100%
  );
  -webkit-mask-image: linear-gradient(to bottom, 
    transparent 0%, 
    black 10%, 
    black 80%, 
    transparent 100%
  );
}
</style>
