import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('Netease likes loading', () => {
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
