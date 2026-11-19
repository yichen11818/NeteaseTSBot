import { afterEach, describe, expect, it, vi } from 'vitest'
import { parseServerCatalog, serverIdFromPath, serverPageUrl } from './servers'

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules() })

describe('server selection', () => {
  it('keeps tab selection in the URL and validates IDs', () => {
    expect(serverIdFromPath('/s/home/queue')).toBe('home')
    expect(serverIdFromPath('/search')).toBe('')
    expect(serverPageUrl('friends')).toBe('/s/friends/search')
    expect(() => serverIdFromPath('/s/..%2fhome/queue')).toThrow()
    expect(() => serverPageUrl('../home')).toThrow()
  })

  it('rejects malformed catalogs and duplicate IDs', () => {
    expect(parseServerCatalog({ servers: [] })).toEqual([])
    expect(parseServerCatalog({ servers: [{ id: 'home', name: '主服务器', password: 'excluded' }] }))
      .toEqual([{ id: 'home', name: '主服务器' }])
    for (const value of [null, {}, { servers: [{ id: 'home', name: '' }] },
      { servers: [{ id: 'home', name: 'A' }, { id: 'home', name: 'B' }] }]) {
      expect(() => parseServerCatalog(value)).toThrow()
    }
  })

  it('does not silently switch an unknown server to the first server', async () => {
    vi.stubGlobal('window', { location: { pathname: '/s/deleted/queue' } })
    const { validateServerSelection } = await import('./servers')
    expect(() => validateServerSelection([{ id: 'home', name: 'Home' }])).toThrow('不在当前清单中')
  })

  it('surfaces a registry outage and leaves demo mode offline', async () => {
    vi.stubEnv('VITE_DEMO_MODE', 'false')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))
    await expect((await import('./servers')).loadServerCatalog()).rejects.toThrow('503')
    vi.stubEnv('VITE_DEMO_MODE', 'true')
    vi.resetModules()
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    expect(await (await import('./servers')).loadServerCatalog()).toEqual([])
    expect(fetch).not.toHaveBeenCalled()
  })

  it('isolates stored account data and quality preferences without changing single-server keys', async () => {
    const { serverStorageKey, routerBase } = await import('./servers')
    vi.stubGlobal('window', { location: { pathname: '/s/home/search' } })
    const home = serverStorageKey('likes')
    expect(routerBase()).toBe('/s/home/')
    vi.stubGlobal('window', { location: { pathname: '/s/friends/search' } })
    expect(serverStorageKey('likes')).not.toBe(home)
    vi.stubGlobal('window', { location: { pathname: '/search' } })
    expect(serverStorageKey('likes')).toBe('likes')
  })
})
