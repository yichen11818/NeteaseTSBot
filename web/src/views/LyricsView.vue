<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { apiGet, apiPost } from '../api'
import LyricsDisplay from '../components/LyricsDisplay.vue'
import { 
  ArrowLeft, 
  Play, 
  Pause, 
  SkipBack, 
  SkipForward,
  Heart,
  MoreHorizontal
} from 'lucide-vue-next'

const router = useRouter()

const trackId = ref<number>(0)
const currentTime = ref<number>(0)
const artwork = ref<string>('')
const title = ref<string>('')
const artist = ref<string>('')
const album = ref<string>('')
const isPlaying = ref<boolean>(false)
const isLiked = ref<boolean>(false)

let timer: number | null = null

async function loadState() {
  try {
    const st = await apiGet<any>('/voice/status')
    trackId.value = Number(st?.track_id ?? 0)
    currentTime.value = Number(st?.current_time ?? 0)
    artwork.value = String(st?.artwork_url || '')
    title.value = String(st?.now_playing_title || '')
    artist.value = String(st?.now_playing_artist || '')
    album.value = String(st?.now_playing_album || '')
    isPlaying.value = st?.state === 'playing'
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

async function toggleLike() {
  if (!trackId.value) return
  try {
    if (isLiked.value) {
      await apiPost(`/likes/${trackId.value}/remove`, {})
    } else {
      await apiPost(`/likes/${trackId.value}/add`, {})
    }
    isLiked.value = !isLiked.value
  } catch (e) {
    console.error('Failed to toggle like:', e)
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
  <div class="relative h-full min-h-[calc(100vh-96px)] overflow-hidden apple-music-lyrics">
    <!-- Dynamic fluid background -->
    <div class="absolute inset-0 bg-cover bg-center scale-110 filter blur-3xl opacity-30" :style="backdropStyle"></div>
    <div class="absolute inset-0 bg-gradient-to-br from-black/80 via-black/60 to-black/90"></div>
    <div class="absolute inset-0 bg-gradient-to-t from-black/95 via-transparent to-black/50"></div>
    
    <!-- Animated background particles -->
    <div class="absolute inset-0 overflow-hidden">
      <div class="absolute top-1/4 left-1/4 w-96 h-96 bg-white/5 rounded-full blur-3xl animate-pulse"></div>
      <div class="absolute bottom-1/3 right-1/3 w-64 h-64 bg-blue-500/10 rounded-full blur-2xl animate-pulse" style="animation-delay: 2s;"></div>
      <div class="absolute top-1/2 right-1/4 w-48 h-48 bg-purple-500/8 rounded-full blur-xl animate-pulse" style="animation-delay: 4s;"></div>
    </div>

    <div class="relative h-full flex flex-col">
      <!-- Minimal header -->
      <header class="flex items-center justify-between px-8 pt-8 pb-6 z-10">
        <button
          @click="goBack"
          class="p-2 rounded-full bg-black/20 backdrop-blur-xl text-white/90 hover:bg-black/30 hover:text-white transition-all duration-300"
        >
          <ArrowLeft :size="18" />
        </button>
        <div class="text-white/60 text-xs font-medium tracking-widest uppercase">Lyrics</div>
        <div class="w-8"></div>
      </header>

      <!-- Main content - Apple Music style layout -->
      <div class="flex-1 min-h-0 px-8 pb-8">
        <div class="h-full max-w-6xl mx-auto">
          <!-- Compact track info at top -->
          <div class="flex items-center gap-6 mb-8">
            <!-- Small album artwork -->
            <div class="relative flex-shrink-0">
              <div class="w-16 h-16 rounded-xl overflow-hidden shadow-lg ring-1 ring-white/20">
                <img v-if="artwork" :src="artwork" :alt="title" class="w-full h-full object-cover" />
                <div v-else class="w-full h-full bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500"></div>
              </div>
            </div>
            
            <!-- Track info -->
            <div class="flex-1 min-w-0">
              <h1 class="text-white text-xl font-semibold tracking-tight truncate">
                {{ title || 'No track playing' }}
              </h1>
              <p class="text-white/60 text-sm font-medium truncate">
                {{ artist || '' }}
              </p>
            </div>

            <!-- Like button only -->
            <div class="flex items-center">
              <button 
                @click="toggleLike"
                :class="[
                  'p-2 rounded-full transition-all duration-200',
                  isLiked 
                    ? 'text-red-400 hover:text-red-300' 
                    : 'text-white/50 hover:text-white/80'
                ]"
              >
                <Heart :size="16" :fill="isLiked ? 'currentColor' : 'none'" />
              </button>
            </div>
          </div>

          <!-- Full-width lyrics display -->
          <div class="h-[calc(100%-120px)]">
            <LyricsDisplay
              :key="trackId"
              :track-id="trackId"
              :current-time="currentTime"
              :is-visible="true"
              :show-header="false"
              theme="apple-music"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
