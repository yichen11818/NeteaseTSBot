<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiGet, apiPost } from '../api'
import { 
  ArrowLeft, 
  Play, 
  Plus, 
  Clock, 
  User, 
  Music,
  Loader2,
  Calendar,
  Heart
} from 'lucide-vue-next'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import EmptyState from '../components/EmptyState.vue'
import { getFavoritePlaylists, getFavoriteSongs, toggleFavoritePlaylist, toggleFavoriteSong } from '../utils/favorites'

const route = useRoute()
const router = useRouter()
const playlistId = route.params.id as string

const loading = ref(true)
const error = ref('')
const status = ref('')
const playlist = ref<any>(null)
const tracks = ref<any[]>([])

const isFavPlaylist = ref(false)
const favSongIds = ref<Set<number>>(new Set())

function refreshFavSongs() {
  favSongIds.value = new Set(getFavoriteSongs().map((s) => Number(s.id)))
}

function isFavSong(track: any): boolean {
  const id = Number(track?.id)
  if (!Number.isFinite(id) || id <= 0) return false
  return favSongIds.value.has(id)
}

function toggleSong(track: any) {
  toggleFavoriteSong(track)
  refreshFavSongs()
}

function refreshFavPlaylist() {
  isFavPlaylist.value = getFavoritePlaylists().some((p) => Number(p.id) === Number(playlistId))
}

function togglePlaylist() {
  if (!playlist.value) return
  toggleFavoritePlaylist({
    id: playlist.value.id,
    name: playlist.value.name,
    coverImgUrl: playlist.value.coverImgUrl,
    playCount: playlist.value.playCount,
    creator: playlist.value.creator,
  })
  refreshFavPlaylist()
}

async function loadPlaylistDetail() {
  loading.value = true
  error.value = ''
  
  try {
    const res = await apiGet<any>(`/netease/playlist/${playlistId}/detail`)
    if (res?.playlist) {
      playlist.value = res.playlist
      tracks.value = res.playlist.tracks || []
      refreshFavSongs()
      refreshFavPlaylist()
    } else {
      error.value = '未找到歌单信息'
    }
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  } finally {
    loading.value = false
  }
}

async function playAll() {
  if (!tracks.value.length) return
  
  // Apply a limit to avoid overwhelming the queue if the playlist is huge
  const tracksToPlay = tracks.value.slice(0, 20)
  
  // 弹窗确认
  const confirmed = confirm(`确定要将歌单《${playlist.value?.name || '未知歌单'}》的前 ${tracksToPlay.length} 首歌曲添加到播放队列并开始播放吗？\n\n歌单共有 ${tracks.value.length} 首歌曲，将添加前 ${tracksToPlay.length} 首。`)
  
  if (!confirmed) {
    return
  }
  
  let addedCount = 0
  
  for (const track of tracksToPlay) {
    await enqueue(track, addedCount === 0) // Play the first one immediately
    addedCount++
  }
  
  status.value = `已添加 ${addedCount} 首歌曲到播放队列`
  setTimeout(() => status.value = '', 3000)
}

async function enqueue(track: any, playNow: boolean = false) {
  try {
    const artist = (track.ar || track.artists || []).map((a: any) => a.name).join(', ')
    await apiPost('/queue/netease', {
      song_id: String(track.id),
      title: track.name,
      artist,
      play_now: playNow,
    })
    
    if (!status.value) { // Don't overwrite bulk status
      status.value = `已添加 "${track.name}" 到队列${playNow ? ' (正在播放)' : ''}`
      setTimeout(() => status.value = '', 3000)
    }
  } catch (e: any) {
    console.error('Failed to enqueue:', e)
    const msg = String(e?.message ?? e)
    alert(`点歌失败: ${msg}`)
  }
}

function formatDuration(dt: number): string {
  if (!dt) return '--:--'
  const date = new Date(dt)
  return `${date.getMinutes()}:${date.getSeconds().toString().padStart(2, '0')}`
}

function formatDate(timestamp: number): string {
  if (!timestamp) return ''
  return new Date(timestamp).toLocaleDateString()
}

function formatCount(count: number): string {
  if (count > 100000000) return `${(count / 100000000).toFixed(1)}亿`
  if (count > 10000) return `${(count / 10000).toFixed(1)}万`
  return String(count)
}

onMounted(() => {
  loadPlaylistDetail()
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50 overflow-hidden relative">
    <!-- Hero Background (Blurred) -->
    <div 
      v-if="playlist"
      class="absolute top-0 left-0 right-0 h-[400px] z-0 overflow-hidden pointer-events-none"
    >
      <div 
        class="absolute inset-0 bg-cover bg-center blur-3xl opacity-30 scale-110"
        :style="{ backgroundImage: `url(${playlist.coverImgUrl})` }"
      ></div>
      <div class="absolute inset-0 bg-gradient-to-b from-white/10 via-gray-50/80 to-gray-50"></div>
    </div>

    <!-- Header / Nav (Transparent) -->
    <div class="relative z-10 px-6 py-4 flex items-center gap-4">
      <button 
        @click="router.back()" 
        class="p-2 bg-white/50 hover:bg-white/80 backdrop-blur-md rounded-full transition-all text-gray-700 shadow-sm"
      >
        <ArrowLeft :size="20" />
      </button>

      <button
        v-if="playlist"
        class="ml-auto p-2 rounded-full backdrop-blur-md shadow-sm transition-colors"
        :class="isFavPlaylist ? 'bg-pink-50 text-pink-600 hover:bg-pink-100' : 'bg-white/50 text-gray-600 hover:bg-pink-50 hover:text-pink-600'"
        :title="isFavPlaylist ? '取消本地收藏' : '本地收藏歌单'"
        @click="togglePlaylist"
      >
        <Heart :size="20" :fill="isFavPlaylist ? 'currentColor' : 'none'" />
      </button>
      <h1 class="text-xl font-bold text-gray-900/80 truncate opacity-0 transition-opacity duration-300" :class="{ 'opacity-100': false }">
        <!-- Optional: Show title on scroll -->
        歌单详情
      </h1>
    </div>

    <div class="relative z-10 flex-1 overflow-y-auto scrollbar-thin px-4 md:px-6 pb-24">
      <div v-if="loading" class="h-64 flex items-center justify-center">
        <LoadingSpinner text="加载歌单详情..." />
      </div>

      <div v-else-if="error" class="h-64 flex items-center justify-center">
        <div class="bg-red-50 border border-red-200 rounded-xl p-6 text-center max-w-md mx-auto">
          <div class="text-red-800 font-medium mb-2">加载失败</div>
          <div class="text-red-600 text-sm mb-4">{{ error }}</div>
          <button @click="loadPlaylistDetail" class="btn-secondary">重试</button>
        </div>
      </div>

      <div v-else-if="playlist" class="max-w-6xl mx-auto">
        <!-- Playlist Info Header -->
        <div class="flex flex-col md:flex-row gap-6 md:gap-8 items-center md:items-end mb-8 md:mb-10 pt-4">
          <!-- Cover -->
          <div class="w-40 h-40 md:w-52 md:h-52 flex-shrink-0 shadow-2xl rounded-2xl overflow-hidden relative group ring-1 ring-black/5">
            <img 
              :src="playlist.coverImgUrl + '?param=400y400'" 
              :alt="playlist.name" 
              class="w-full h-full object-cover"
            />
            <div class="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors duration-300"></div>
            <div class="absolute top-3 right-3 bg-black/60 backdrop-blur-md text-white text-xs px-2.5 py-1 rounded-full flex items-center gap-1 font-medium shadow-sm">
              <Play :size="10" fill="currentColor" />
              {{ formatCount(playlist.playCount) }}
            </div>
          </div>

          <!-- Info -->
          <div class="flex-1 flex flex-col items-center md:items-start text-center md:text-left min-w-0">
            <h2 class="text-2xl md:text-4xl lg:text-5xl font-black text-gray-900 mb-3 md:mb-4 leading-tight tracking-tight">
              {{ playlist.name }}
            </h2>
            
            <div class="flex items-center gap-3 mb-4 md:mb-6 text-gray-600">
              <img 
                v-if="playlist.creator?.avatarUrl" 
                :src="playlist.creator.avatarUrl + '?param=50y50'" 
                class="w-8 h-8 rounded-full shadow-sm"
              />
              <span class="font-semibold text-gray-800">{{ playlist.creator?.nickname }}</span>
              <span class="text-gray-300 mx-1">•</span>
              <span class="text-sm text-gray-500">{{ formatDate(playlist.createTime) }} 创建</span>
              <span class="text-gray-300 mx-1">•</span>
              <span class="text-sm text-gray-500">{{ tracks.length }} 首歌曲</span>
            </div>

            <p v-if="playlist.description" class="text-sm text-gray-500 mb-6 md:mb-8 line-clamp-2 max-w-2xl leading-relaxed">
              {{ playlist.description }}
            </p>

            <div class="flex gap-4">
              <button @click="playAll" class="btn-primary px-8 py-3 text-lg shadow-lg shadow-blue-500/30 hover:shadow-blue-500/40 hover:-translate-y-0.5 transition-all w-full md:w-auto flex justify-center">
                <Play :size="20" fill="currentColor" />
                播放全部
              </button>
              <button
                @click="togglePlaylist"
                class="btn-secondary px-6 shadow-sm hover:shadow"
                :class="isFavPlaylist ? 'bg-pink-50 text-pink-700 border-pink-200' : ''"
              >
                <Heart :size="20" :fill="isFavPlaylist ? 'currentColor' : 'none'" />
                {{ isFavPlaylist ? '已收藏' : '本地收藏' }}
              </button>
              <!-- <button class="btn-secondary px-6 shadow-sm hover:shadow">
                <Heart :size="20" />
                收藏
              </button> -->
            </div>
          </div>
        </div>

        <!-- Track List -->
        <div class="bg-white/50 backdrop-blur-xl rounded-2xl border border-white/60 shadow-xl shadow-gray-200/50 overflow-hidden">
          <div v-if="status" class="status-success m-4 mb-0 shadow-sm">
            {{ status }}
          </div>

          <table class="w-full text-left border-collapse">
            <thead class="text-gray-400 text-xs uppercase font-semibold border-b border-gray-100 hidden md:table-header-group">
              <tr>
                <th class="px-3 md:px-6 py-4 w-16 text-center font-medium">#</th>
                <th class="px-3 md:px-6 py-4 font-medium">标题</th>
                <th class="px-3 md:px-6 py-4 hidden md:table-cell font-medium">歌手</th>
                <th class="px-3 md:px-6 py-4 hidden lg:table-cell font-medium">专辑</th>
                <th class="px-3 md:px-6 py-4 w-24 text-right font-medium">时长</th>
                <th class="px-3 md:px-6 py-4 w-24"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <tr 
                v-for="(track, index) in tracks" 
                :key="track.id" 
                class="group hover:bg-blue-50/50 transition-colors duration-200"
              >
                <td class="px-3 md:px-6 py-3 md:py-4 text-center text-gray-400 text-sm group-hover:text-blue-600 font-medium w-10 md:w-16">
                  {{ index + 1 }}
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4">
                  <div class="font-semibold text-gray-900 line-clamp-1 text-base">{{ track.name }}</div>
                  <div class="text-xs text-gray-500 md:hidden line-clamp-1 mt-1">
                    {{ (track.ar || []).map((a: any) => a.name).join(', ') }}
                  </div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-600 hidden md:table-cell max-w-[200px]">
                  <div class="truncate hover:text-gray-900 transition-colors">
                    {{ (track.ar || []).map((a: any) => a.name).join(', ') }}
                  </div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-500 hidden lg:table-cell max-w-[200px]">
                  <div class="truncate hover:text-gray-700 transition-colors">{{ track.al?.name }}</div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-right text-sm text-gray-400 font-mono tabular-nums">
                  {{ formatDuration(track.dt) }}
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-right">
                  <div class="flex items-center justify-end gap-2 md:opacity-0 group-hover:opacity-100 transition-all duration-200 md:transform md:translate-x-2 group-hover:translate-x-0">
                    <button 
                      @click="enqueue(track, true)"
                      class="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-100/50 rounded-lg transition-colors"
                      title="立即播放"
                    >
                      <Play :size="18" />
                    </button>
                    <button 
                      @click="enqueue(track, false)"
                      class="p-2 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                      title="添加到队列"
                    >
                      <Plus :size="18" />
                    </button>
                    <button
                      @click="toggleSong(track)"
                      class="p-2 rounded-lg transition-colors"
                      :class="isFavSong(track) ? 'text-pink-600 bg-pink-50 hover:bg-pink-100' : 'text-gray-400 hover:text-pink-600 hover:bg-pink-50'"
                      :title="isFavSong(track) ? '取消本地收藏' : '本地收藏'"
                    >
                      <Heart :size="18" :fill="isFavSong(track) ? 'currentColor' : 'none'" />
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          
          <div v-if="!tracks.length" class="p-16 text-center text-gray-400">
            <Music :size="48" class="mx-auto mb-4 opacity-20" />
            <p>暂无歌曲</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
