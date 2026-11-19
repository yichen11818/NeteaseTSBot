import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const cacheKey = 'tsbot:server:local:tsbot_likes_cache'

beforeEach(() => {
  vi.stubEnv('VITE_DEMO_MODE', 'false')
  vi.stubGlobal('window', { location: { pathname: '/s/local/likes' } })
  const store = new Map([['tsbot:server:local:tsbot_user_netease_cookie', 'cookie']])
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => store.set(key, value),
    removeItem: (key: string) => store.delete(key),
  })
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('Netease likes loading', () => {
  it('discards the old first-page cache before searching the full collection', async () => {
    localStorage.setItem(cacheKey, JSON.stringify({
      timestamp: Date.now(), data: { songs: [{ id: 1 }], total: 401, has_more: true, limit: 200 },
    }))
    const data = { songs: Array.from({ length: 401 }, (_, id) => ({ id })), has_more: false }
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(data))))
    vi.stubGlobal('fetch', fetch)
    const { useNeteaseLikes } = await import('./useNeteaseLikes')
    const likes = useNeteaseLikes()
    await likes.load()
    expect(likes.likes.value.songs).toHaveLength(401)
    expect(fetch).toHaveBeenCalledOnce()
    await likes.load()
    expect(fetch).toHaveBeenCalledOnce()
    await likes.load(true)
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('does not cache an incomplete response as a complete collection', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      songs: [{ id: 1 }], has_more: true,
    }))))
    const { useNeteaseLikes } = await import('./useNeteaseLikes')
    const likes = useNeteaseLikes()
    await likes.load()
    expect(likes.error.value).toContain('未完整加载')
    expect(likes.likes.value).toBeNull()
    expect(localStorage.getItem(cacheKey)).toBeNull()
  })

  it('does not reuse cached account data after logout', async () => {
    localStorage.setItem(cacheKey, JSON.stringify({
      version: 2, timestamp: Date.now(), data: { songs: [{ id: 1 }], has_more: false },
    }))
    localStorage.removeItem('tsbot:server:local:tsbot_user_netease_cookie')
    const { useNeteaseLikes } = await import('./useNeteaseLikes')
    const likes = useNeteaseLikes()
    await likes.load()
    expect(likes.error.value).toContain('Cookie')
    expect(likes.likes.value).toBeNull()
  })
  it('loads the full collection for the current server so sorting applies to every favorite', async () => {
    vi.stubEnv('VITE_DEMO_MODE', 'false')
    vi.stubGlobal('window', { location: { pathname: '/s/local/search' } })
    const store = new Map<string, string>([
      ['tsbot:server:local:tsbot_user_netease_cookie', 'cookie'],
    ])
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => store.set(key, value),
      removeItem: (key: string) => store.delete(key),
    })
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      songs: [],
      offset: 0,
      limit: 0,
      has_more: false,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    const { useNeteaseLikes } = await import('./useNeteaseLikes')
    await useNeteaseLikes().load(false)

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][0]).toContain('/api/servers/local/netease/likes?offset=0&limit=0')
  })
})
