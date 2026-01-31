<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Heart,
  Music,
  ListMusic,
  Trash2,
  Play,
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import { apiPost } from '../api'
import {
  getFavoritePlaylists,
  getFavoriteSongs,
  removeFavoritePlaylist,
  removeFavoriteSong,
  toggleFavoritePlaylist,
  toggleFavoriteSong,
  type FavoritePlaylist,
  type FavoriteSong,
} from '../utils/favorites'

const router = useRouter()

const activeTab = ref<'songs' | 'playlists'>('songs')
const songs = ref<FavoriteSong[]>([])
const playlists = ref<FavoritePlaylist[]>([])
const error = ref('')

function refresh() {
  songs.value = getFavoriteSongs()
  playlists.value = getFavoritePlaylists()
}

const sortedSongs = computed(() => {
  return [...songs.value].sort((a, b) => Number(b._fav_at || 0) - Number(a._fav_at || 0))
})

const sortedPlaylists = computed(() => {
  return [...playlists.value].sort((a, b) => Number(b._fav_at || 0) - Number(a._fav_at || 0))
})

function formatDuration(durationMs?: number): string {
  const ms = Number(durationMs)
  if (!Number.isFinite(ms) || ms <= 0) return '--:--'
  const minutes = Math.floor(ms / 60000)
  const seconds = Math.floor((ms % 60000) / 1000)
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

async function playSong(song: FavoriteSong) {
  try {
    const artist = (song.ar || []).map((a) => a.name).join(', ')
    await apiPost('/queue/netease', {
      song_id: String(song.id),
      title: song.name,
      artist,
      play_now: true,
    })
  } catch (e: any) {
    const msg = String(e?.message ?? e)
    error.value = msg
    alert(`点歌失败: ${msg}`)
  }
}

function openPlaylist(playlist: FavoritePlaylist) {
  void router.push(`/playlist/${playlist.id}`)
}

function unfavSong(id: number) {
  removeFavoriteSong(id)
  refresh()
}

function unfavPlaylist(id: number) {
  removeFavoritePlaylist(id)
  refresh()
}

function togglePlaylist(pl: FavoritePlaylist) {
  toggleFavoritePlaylist(pl)
  refresh()
}

function toggleSong(s: FavoriteSong) {
  toggleFavoriteSong(s)
  refresh()
}

onMounted(refresh)
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50">
    <div class="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 z-20 shadow-sm">
      <div class="flex items-center gap-3">
        <Heart :size="26" class="text-pink-600" fill="currentColor" />
        <h1 class="text-2xl font-bold text-gray-900 tracking-tight">本地收藏</h1>
      </div>

      <div class="flex items-center gap-2">
        <button
          class="btn-secondary text-sm py-1.5 px-3"
          :class="activeTab === 'songs' ? 'bg-pink-50 text-pink-700 border-pink-200' : ''"
          @click="activeTab = 'songs'"
        >
          <Music :size="16" />
          <span class="hidden sm:inline">歌曲</span>
        </button>

        <button
          class="btn-secondary text-sm py-1.5 px-3"
          :class="activeTab === 'playlists' ? 'bg-pink-50 text-pink-700 border-pink-200' : ''"
          @click="activeTab = 'playlists'"
        >
          <ListMusic :size="16" />
          <span class="hidden sm:inline">歌单</span>
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto px-4 md:px-6 py-4 md:py-6 pb-24 scrollbar-thin">
      <div v-if="error" class="mb-6 bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
        {{ error }}
      </div>

      <template v-if="activeTab === 'songs'">
        <EmptyState
          v-if="sortedSongs.length === 0"
          :icon="Music"
          title="暂无本地收藏歌曲"
          description="你可以在搜索结果或歌单详情里点击心形收藏到本地"
        />

        <div v-else class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden max-w-6xl mx-auto">
          <table class="w-full text-left border-collapse">
            <thead class="bg-gray-50/50 text-gray-400 text-xs uppercase font-semibold border-b border-gray-100 hidden md:table-header-group">
              <tr>
                <th class="px-3 md:px-6 py-4 font-medium w-16">#</th>
                <th class="px-3 md:px-6 py-4 font-medium">标题</th>
                <th class="px-3 md:px-6 py-4 font-medium hidden md:table-cell">歌手</th>
                <th class="px-3 md:px-6 py-4 font-medium hidden lg:table-cell">专辑</th>
                <th class="px-3 md:px-6 py-4 font-medium w-24 text-right">时长</th>
                <th class="px-3 md:px-6 py-4 font-medium w-32"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <tr
                v-for="(song, index) in sortedSongs"
                :key="song.id"
                class="group hover:bg-pink-50/30 transition-colors duration-200"
              >
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-400 text-center font-medium group-hover:text-pink-600 w-10 md:w-16">
                  {{ index + 1 }}
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4">
                  <div class="flex items-center gap-3 md:gap-4">
                    <div class="w-10 h-10 rounded-lg overflow-hidden flex-shrink-0 shadow-sm bg-gray-100">
                      <img
                        v-if="song.al?.picUrl"
                        :src="song.al.picUrl + '?param=100y100'"
                        :alt="song.name"
                        class="w-full h-full object-cover"
                      />
                      <div v-else class="w-full h-full bg-gradient-to-br from-pink-200 to-rose-200 flex items-center justify-center">
                        <Music :size="16" class="text-pink-500" />
                      </div>
                    </div>
                    <div class="min-w-0">
                      <div class="font-semibold text-gray-900 line-clamp-1 text-sm group-hover:text-pink-700 transition-colors">{{ song.name }}</div>
                      <div class="text-xs text-gray-500 md:hidden line-clamp-1 mt-0.5">
                        {{ (song.ar || []).map((a: any) => a.name).join(', ') }}
                      </div>
                    </div>
                  </div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-600 hidden md:table-cell">
                  <div class="truncate max-w-[150px]">{{ (song.ar || []).map((a: any) => a.name).join(', ') }}</div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-sm text-gray-500 hidden lg:table-cell">
                  <div class="truncate max-w-[150px]">{{ song.al?.name }}</div>
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-right text-sm text-gray-400 font-mono tabular-nums">
                  {{ formatDuration(song.dt) }}
                </td>
                <td class="px-3 md:px-6 py-3 md:py-4 text-right">
                  <div class="flex items-center justify-end gap-2 md:opacity-0 group-hover:opacity-100 transition-all duration-200">
                    <button
                      class="p-2 text-gray-400 hover:text-pink-600 hover:bg-pink-50 rounded-lg transition-colors"
                      title="立即播放"
                      @click="playSong(song)"
                    >
                      <Play :size="18" />
                    </button>

                    <button
                      class="p-2 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                      title="取消收藏"
                      @click="unfavSong(song.id)"
                    >
                      <Trash2 :size="18" />
                    </button>

                    <button
                      class="p-2 text-pink-600 bg-pink-50 rounded-lg transition-colors"
                      title="已收藏"
                      @click="toggleSong(song)"
                    >
                      <Heart :size="18" fill="currentColor" />
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <template v-else>
        <EmptyState
          v-if="sortedPlaylists.length === 0"
          :icon="ListMusic"
          title="暂无本地收藏歌单"
          description="你可以在歌单广场或歌单详情页点击心形收藏到本地"
        />

        <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 md:gap-6 max-w-[1600px] mx-auto">
          <div
            v-for="pl in sortedPlaylists"
            :key="pl.id"
            class="group relative flex flex-col gap-3"
          >
            <div
              class="relative aspect-square rounded-xl overflow-hidden shadow-sm transition-all duration-300 group-hover:shadow-xl group-hover:-translate-y-1 cursor-pointer"
              @click="openPlaylist(pl)"
            >
              <img
                v-if="pl.coverImgUrl || pl.picUrl"
                :src="(pl.coverImgUrl || pl.picUrl) + '?param=300y300'"
                :alt="pl.name"
                class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
              />
              <div v-else class="w-full h-full bg-gradient-to-br from-pink-200 to-rose-200 flex items-center justify-center">
                <ListMusic :size="24" class="text-pink-600" />
              </div>
            </div>

            <div class="min-w-0">
              <h3 class="font-bold text-gray-900 text-sm line-clamp-2 leading-snug group-hover:text-pink-700 transition-colors mb-1" :title="pl.name">
                {{ pl.name }}
              </h3>
              <p class="text-xs text-gray-500 truncate">{{ pl.creator?.nickname }}</p>
            </div>

            <div class="flex items-center gap-2">
              <button
                class="btn-secondary text-xs py-1 px-2 flex-1 justify-center"
                @click="openPlaylist(pl)"
              >
                查看
              </button>
              <button
                class="btn-secondary text-xs py-1 px-2"
                title="取消收藏"
                @click="unfavPlaylist(pl.id)"
              >
                <Trash2 :size="14" />
              </button>
              <button
                class="btn-secondary text-xs py-1 px-2 bg-pink-50 text-pink-700 border-pink-200"
                title="已收藏"
                @click="togglePlaylist(pl)"
              >
                <Heart :size="14" fill="currentColor" />
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
