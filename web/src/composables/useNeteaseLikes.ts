import { ref } from 'vue'
import { apiGet } from '../api'
import { DEMO_MODE } from '../demoMode'
import { readServerStorage, serverStorageKey } from '../servers'

const USER_COOKIE_KEY = 'tsbot_user_netease_cookie'
const LIKES_CACHE_KEY = serverStorageKey('tsbot_likes_cache')
const CACHE_DURATION_MS = 150 * 60 * 1000
const CACHE_VERSION = 2

function readCachedLikes(): any | null {
  const cached = localStorage.getItem(LIKES_CACHE_KEY)
  if (!cached) return null
  const { data, timestamp, version } = JSON.parse(cached)
  if (version === CACHE_VERSION && Array.isArray(data?.songs) && data?.has_more === false
    && Date.now() - timestamp <= CACHE_DURATION_MS) return data
  localStorage.removeItem(LIKES_CACHE_KEY)
  return null
}

async function requestLikes(useCache: boolean): Promise<any> {
  const cookie = readServerStorage(USER_COOKIE_KEY)
  if (!cookie && !DEMO_MODE) throw new Error('需要先设置网易云音乐 Cookie')
  const cached = useCache ? readCachedLikes() : null
  if (cached) return cached
  const data = await apiGet<any>('/netease/likes?offset=0&limit=0', { 'X-Netease-Cookie': cookie })
  if (!Array.isArray(data?.songs) || data?.has_more !== false) {
    throw new Error('网易云收藏未完整加载，请刷新重试')
  }
  localStorage.setItem(LIKES_CACHE_KEY, JSON.stringify({ data, timestamp: Date.now(), version: CACHE_VERSION }))
  return data
}

export function useNeteaseLikes() {
  const error = ref('')
  const likes = ref<any>(null)
  const loading = ref(false)

  async function load(forceRefresh = false) {
    if (loading.value) return
    loading.value = true
    error.value = ''
    likes.value = null
    try {
      likes.value = await requestLikes(!forceRefresh)
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
      loading.value = false
    }
  }

  return { error, likes, loading, load }
}
