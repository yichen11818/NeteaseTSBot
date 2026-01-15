<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { apiGet } from '../api'

interface LyricLine {
  time: number
  text: string
}

const props = defineProps<{
  trackId?: number
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
async function loadLyrics(trackId: number) {
  if (!trackId) return
  
  loading.value = true
  error.value = ''
  
  try {
    const response = await apiGet<{ lyrics: LyricLine[] }>(`/lyrics/${trackId}`)
    lyrics.value = response.lyrics || []
  } catch (e: any) {
    error.value = String(e?.message ?? e)
    lyrics.value = []
  } finally {
    loading.value = false
  }
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
  
  if (theme.value === 'apple-music') {
    if (isCurrent) {
      return {
        textShadow: '0 0 40px rgba(255,255,255,0.4), 0 0 80px rgba(255,255,255,0.2)',
        fontWeight: '700',
        letterSpacing: '-0.02em'
      }
    } else if (isPast) {
      return {
        fontWeight: '400'
      }
    } else {
      return {
        fontWeight: '500'
      }
    }
  } else if (theme.value === 'dark') {
    return {
      textShadow: isCurrent ? '0 0 20px rgba(255,255,255,0.3)' : 'none'
    }
  }
  
  return {}
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
              'transition-all duration-700 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] leading-snug cursor-pointer origin-center',
              theme === 'apple-music'
                ? [
                    'text-center font-semibold tracking-wide text-xl md:text-3xl',
                    index === currentLineIndex
                      ? 'text-white opacity-100 transform scale-110 blur-none drop-shadow-[0_0_15px_rgba(255,255,255,0.15)]'
                      : index < currentLineIndex
                      ? 'text-white/40 opacity-40 transform scale-95 blur-[0.5px]'
                      : 'text-white/60 opacity-60 transform scale-95 blur-[0.5px]'
                  ]
                : theme === 'dark'
                ? [
                    'text-center hover:scale-[1.02]',
                    index === currentLineIndex
                      ? 'text-white font-bold text-2xl lg:text-3xl scale-110 drop-shadow-lg transform translate-y-0 opacity-100'
                      : index < currentLineIndex
                      ? 'text-white/30 text-lg lg:text-xl opacity-60 transform translate-y-1'
                      : 'text-white/60 text-lg lg:text-xl opacity-80 transform translate-y-0'
                  ]
                : [
                    'text-center hover:scale-[1.02]',
                    index === currentLineIndex
                      ? 'text-blue-600 font-bold text-2xl scale-110'
                      : index < currentLineIndex
                      ? 'text-gray-400 text-lg opacity-60'
                      : 'text-gray-600 text-lg opacity-80'
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
</style>
