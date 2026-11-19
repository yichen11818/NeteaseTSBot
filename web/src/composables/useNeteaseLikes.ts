import { ref } from 'vue'
import { apiGet } from '../api'
import { DEMO_MODE } from '../demoMode'
import { readServerStorage, serverStorageKey } from '../servers'

const USER_COOKIE_KEY = 'tsbot_user_netease_cookie'
const LIKES_CACHE_KEY = serverStorageKey('tsbot_likes_cache')
const CACHE_DURATION_MS = 150 * 60 * 1000
const PAGE_SIZE = 200

function readCachedLikes(): any | null {
  const cached = localStorage.getItem(LIKES_CACHE_KEY)
  if (!cached) return null
  const { data, timestamp } = JSON.parse(cached)
  if (Date.now() - timestamp <= CACHE_DURATION_MS) return data
  localStorage.removeItem(LIKES_CACHE_KEY)
  return null
}

async function requestLikes(offset: number, limit: number, useCache: boolean): Promise<any> {
  const cached = useCache ? readCachedLikes() : null
  if (cached) return cached
  const cookie = readServerStorage(USER_COOKIE_KEY)
  if (!cookie && !DEMO_MODE) throw new Error('需要先设置网易云音乐 Cookie')
  const data = await apiGet<any>(`/netease/likes?offset=${offset}&limit=${limit}`, { 'X-Netease-Cookie': cookie })
  if (offset === 0) localStorage.setItem(LIKES_CACHE_KEY, JSON.stringify({ data, timestamp: Date.now() }))
  return data
}

export function useNeteaseLikes() {
  const error = ref('')
  const likes = ref<any>(null)
  const loading = ref(false)
  const offset = ref(0)
  const hasMore = ref(false)

  async function loadPage(reset: boolean, forceRefresh = false) {
    if (loading.value || (!reset && !hasMore.value)) return
    loading.value = true
    error.value = ''
    if (reset) { likes.value = null; offset.value = 0; hasMore.value = false }
    try {
      const data = await requestLikes(
        reset ? 0 : offset.value,
        reset ? 0 : PAGE_SIZE,
        reset && !forceRefresh,
      )
      const previousSongs = likes.value?.songs || []
      likes.value = reset ? data : { ...likes.value, ...data, songs: [...previousSongs, ...(data.songs || [])] }
      offset.value = Number(data?.offset ?? offset.value) + (Number(data?.limit ?? 0) || PAGE_SIZE)
      hasMore.value = Boolean(data?.has_more)
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
      loading.value = false
    }
  }

  return {
    error, likes, loading, hasMore,
    load: (forceRefresh = false) => loadPage(true, forceRefresh),
    loadMore: () => loadPage(false),
  }
}
