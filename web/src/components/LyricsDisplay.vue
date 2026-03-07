<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { apiGet } from '../api'

interface LyricLine {
  time: number
  text: string
}

const props = defineProps<{
  trackId?: number | string
  currentTime: number
  isVisible: boolean
  showHeader?: boolean
  theme?: 'light' | 'dark' | 'apple-music'
}>()

const showHeader = computed(() => props.showHeader !== false)
const theme = computed(() => props.theme || 'light')

const lyrics = ref<LyricLine[]>([])
const loading = ref(false)
const error = ref('')
const lyricsContainer = ref<HTMLElement>()
const isUserScrolling = ref(false)
const scrollTimeout = ref<number | null>(null)

// Find current lyric line
const currentLineIndex = computed(() => {
  if (!lyrics.value.length) return -1
  
  let index = -1
  for (let i = 0; i < lyrics.value.length; i++) {
    if (lyrics.value[i].time <= props.currentTime) {
      index = i
    } else {
      break
    }
  }
  return index
})

// Load lyrics for current track
async function loadLyrics(trackId: number | string) {
  if (!trackId) return
  
  loading.value = true
  error.value = ''
  
  try {
    let response: any
    
    // Detect platform based on trackId format
    if (typeof trackId === 'string' && (trackId.startsWith('qqmusic:') || trackId.includes('qqmusic'))) {
      // QQ Music track
      const songMid = trackId.replace('qqmusic:', '')
      const qqResponse = await apiGet<{ lyric: any }>(`/qqmusic/song/${songMid}/lyric?parse=true`)
      
      // Convert QQ Music lyric format to our format
      if (qqResponse.lyric && qqResponse.lyric.lyric) {
        lyrics.value = qqResponse.lyric.lyric.map((line: any) => ({
          time: parseTimeToMs(line.time),
          text: line.lyric || ''
        })).filter((line: LyricLine) => line.text.trim())
      } else {
        lyrics.value = []
      }
    } else {
      // Netease track (legacy format)
      const numericId = typeof trackId === 'string' ? trackId.replace('netease:', '') : trackId
      response = await apiGet<{ lyrics: LyricLine[] }>(`/lyrics/${numericId}`)
      lyrics.value = response.lyrics || []
    }
  } catch (e: any) {
    error.value = String(e?.message ?? e)
    lyrics.value = []
  } finally {
    loading.value = false
  }
}

// Helper function to parse time string to milliseconds
function parseTimeToMs(timeStr: string): number {
  if (!timeStr) return 0
  
  // Parse time format like "00:30.50" or "01:23.45"
  const parts = timeStr.split(':')
  if (parts.length !== 2) return 0
  
  const minutes = parseInt(parts[0], 10) || 0
  const seconds = parseFloat(parts[1]) || 0
  
  return (minutes * 60 + seconds) * 1000
}
// Auto-scroll to current line
function scrollToCurrentLine() {
  if (currentLineIndex.value >= 0 && lyricsContainer.value && !isUserScrolling.value) {
    const container = lyricsContainer.value
    // Access the inner wrapper's children (the lines)
    const linesWrapper = container.children[0]
    if (!linesWrapper) return
    
    const currentLine = linesWrapper.children[currentLineIndex.value] as HTMLElement
    
    if (currentLine) {
      // Calculate scroll position manually to avoid affecting parent/window scroll
      // Use offsetTop if container is positioned, or getBoundingClientRect difference
      const containerHeight = container.clientHeight
      const lineHeight = currentLine.offsetHeight
      // Since the container scrolls, we need the line's position relative to the container content start
      // offsetTop is usually robust enough if the container is the offsetParent or if structure is simple
      // But to be safe with getBoundingClientRect:
      // scrollTop = currentScroll + (lineTop - containerTop) - (halfContainer - halfLine)
      
      // We can use offsetTop directly since the line is inside the scrollable container
      const targetScroll = currentLine.offsetTop - (containerHeight / 2) + (lineHeight / 2)
      
      container.scrollTo({
        top: targetScroll,
        behavior: 'smooth'
      })
    }
  }
}

// Handle user scroll events
function handleScroll() {
  isUserScrolling.value = true
  
  // Clear existing timeout
  if (scrollTimeout.value) {
    clearTimeout(scrollTimeout.value)
  }
  
  // Set new timeout to resume auto-scrolling after 3 seconds
  scrollTimeout.value = window.setTimeout(() => {
    isUserScrolling.value = false
    scrollToCurrentLine()
  }, 3000)
}

// Handle touch events for mobile
function handleTouchStart() {
  isUserScrolling.value = true
  if (scrollTimeout.value) {
    clearTimeout(scrollTimeout.value)
  }
}

function handleTouchEnd() {
  scrollTimeout.value = window.setTimeout(() => {
    isUserScrolling.value = false
    scrollToCurrentLine()
  }, 3000)
}

// Watch for track changes
watch(() => props.trackId, (newTrackId) => {
  if (newTrackId) {
    loadLyrics(newTrackId)
  }
}, { immediate: true })

// Watch for time changes to auto-scroll
watch(currentLineIndex, () => {
  if (props.isVisible) {
    scrollToCurrentLine()
  }
})

// Get dynamic styling for each line
function getLineStyle(index: number) {
  const isCurrent = index === currentLineIndex.value
  const isPast = index < currentLineIndex.value
  const isNext = index === currentLineIndex.value + 1
  
  if (theme.value === 'apple-music') {
    if (isCurrent) {
      return {
        textShadow: '0 0 40px rgba(255,255,255,0.6), 0 0 80px rgba(255,255,255,0.3), 0 4px 8px rgba(0,0,0,0.3)',
        fontWeight: '700',
        letterSpacing: '-0.02em',
        animation: 'glow 2s ease-in-out infinite alternate'
      }
    } else if (isPast) {
      return {
        fontWeight: '400',
        opacity: '0.4',
        filter: 'blur(0.5px)'
      }
    } else if (isNext) {
      return {
        fontWeight: '600',
        opacity: '0.8',
        textShadow: '0 0 20px rgba(255,255,255,0.2)'
      }
    } else {
      return {
        fontWeight: '500',
        opacity: '0.6'
      }
    }
  } else if (theme.value === 'dark') {
    return {
      textShadow: isCurrent ? '0 0 30px rgba(255,255,255,0.5), 0 0 60px rgba(255,255,255,0.3)' : 'none',
      animation: isCurrent ? 'pulse-dark 1.5s ease-in-out infinite' : 'none'
    }
  }
  
  return {
    animation: isCurrent ? 'pulse-light 1.5s ease-in-out infinite' : 'none'
  }
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div v-if="showHeader" class="flex-shrink-0 p-4 border-b border-gray-200">
      <h3 class="text-lg font-semibold text-gray-900">歌词</h3>
    </div>
    
    <!-- Content -->
    <div class="relative flex-1 overflow-hidden">
      <div
        v-if="theme === 'dark'"
        class="pointer-events-none absolute inset-x-0 top-0 h-12 bg-gradient-to-b from-black/50 to-transparent z-10"
      ></div>
      <div
        v-if="theme === 'dark'"
        class="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/50 to-transparent z-10"
      ></div>

      <!-- Loading state -->
      <div v-if="loading" class="flex items-center justify-center h-full">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
      
      <!-- Error state -->
      <div v-else-if="error" class="flex items-center justify-center h-full p-4">
        <div class="text-center">
          <div :class="theme === 'dark' ? 'text-white/80' : 'text-gray-500'" class="mb-2">无法加载歌词</div>
          <div :class="theme === 'dark' ? 'text-white/60' : 'text-gray-400'" class="text-sm">{{ error }}</div>
        </div>
      </div>
      
      <!-- No lyrics -->
      <div v-else-if="!lyrics.length" class="flex items-center justify-center h-full">
        <div :class="theme === 'dark' ? 'text-white/70' : 'text-gray-500'" class="text-center">
          <div class="mb-2">暂无歌词</div>
          <div :class="theme === 'dark' ? 'text-white/50' : 'text-gray-400'" class="text-sm">该歌曲暂时没有歌词信息</div>
        </div>
      </div>
      
      <!-- Lyrics display -->
      <div 
        v-else 
        class="h-full overflow-y-auto scrollbar-hide relative" 
        ref="lyricsContainer" 
        :class="theme === 'apple-music' ? 'py-8 md:py-16' : 'py-8 md:py-12'"
        @scroll="handleScroll"
        @touchstart="handleTouchStart"
        @touchend="handleTouchEnd"
      >
        <div :class="theme === 'apple-music' ? 'space-y-8 md:space-y-12 px-4 md:px-16' : 'space-y-4 md:space-y-6 px-4 md:px-8'">
          <div
            v-for="(line, index) in lyrics"
            :key="index"
            :class="[
              'transition-all duration-500 ease-[cubic-bezier(0.23,1,0.32,1)] leading-snug cursor-pointer origin-center',
              'hover:duration-300',
              theme === 'apple-music'
                ? [
                    'text-center font-semibold tracking-wide text-xl md:text-3xl',
                    index === currentLineIndex
                      ? 'text-white opacity-100 transform scale-110 blur-none drop-shadow-[0_0_20px_rgba(255,255,255,0.25)] animate-in fade-in slide-in-from-bottom-2 duration-500'
                      : index < currentLineIndex
                      ? 'text-white/40 opacity-30 transform scale-95 blur-[0.8px] translate-y-1'
                      : 'text-white/70 opacity-70 transform scale-98 blur-[0.3px] translate-y-0 hover:scale-100 hover:opacity-80'
                  ]
                : theme === 'dark'
                ? [
                    'text-center hover:scale-[1.02] hover:duration-200',
                    index === currentLineIndex
                      ? 'text-white font-bold text-2xl lg:text-3xl scale-110 drop-shadow-[0_8px_16px_rgba(0,0,0,0.4)] transform translate-y-0 opacity-100 animate-pulse'
                      : index < currentLineIndex
                      ? 'text-white/20 text-lg lg:text-xl opacity-50 transform translate-y-2 scale-95'
                      : 'text-white/60 text-lg lg:text-xl opacity-70 transform translate-y-0 hover:scale-105 hover:text-white/80'
                  ]
                : [
                    'text-center hover:scale-[1.02] hover:duration-200',
                    index === currentLineIndex
                      ? 'text-blue-600 font-bold text-2xl scale-110 drop-shadow-[0_4px_8px_rgba(59,130,246,0.3)] animate-bounce'
                      : index < currentLineIndex
                      ? 'text-gray-300 text-lg opacity-60 transform translate-y-1'
                      : 'text-gray-600 text-lg opacity-80 hover:scale-105 hover:text-blue-500'
                  ]
            ]"
            :style="getLineStyle(index)"
          >
            {{ line.text }}
          </div>
          
          <!-- Bottom spacing for better scrolling -->
          <div :class="theme === 'apple-music' ? 'h-48' : 'h-32'"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scrollbar-hide {
  /* Hide scrollbar for Chrome, Safari and Opera */
  -webkit-scrollbar: none;
  /* Hide scrollbar for IE, Edge and Firefox */
  -ms-overflow-style: none;
  scrollbar-width: none;
}

.scrollbar-hide::-webkit-scrollbar {
  display: none;
}

/* Custom animations */
@keyframes glow {
  0% {
    filter: brightness(1) drop-shadow(0 0 20px rgba(255,255,255,0.3));
  }
  100% {
    filter: brightness(1.2) drop-shadow(0 0 40px rgba(255,255,255,0.6));
  }
}

@keyframes pulse-dark {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.9;
    transform: scale(1.02);
  }
}

@keyframes pulse-light {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.8;
    transform: scale(1.01);
  }
}

/* Enhanced transitions */
.lyric-line-enter-active,
.lyric-line-leave-active {
  transition: all 0.5s cubic-bezier(0.23, 1, 0.32, 1);
}

.lyric-line-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.9);
}

.lyric-line-leave-to {
  opacity: 0;
  transform: translateY(-20px) scale(0.9);
}

/* Hover effects */
.lyric-line:hover {
  transition: all 0.3s ease;
}

/* Current line emphasis */
.current-line {
  animation: currentLineGlow 2s ease-in-out infinite;
}

@keyframes currentLineGlow {
  0%, 100% {
    text-shadow: 0 0 20px currentColor, 0 0 40px currentColor;
  }
  50% {
    text-shadow: 0 0 30px currentColor, 0 0 60px currentColor, 0 0 80px currentColor;
  }
}
</style>
