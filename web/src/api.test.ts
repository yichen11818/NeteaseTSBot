import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules() })

describe('API transport isolation', () => {
  it('routes demo requests locally and rejects credentials without ever fetching', async () => {
    vi.stubEnv('VITE_DEMO_MODE', 'true')
    vi.resetModules()
    const fetch = vi.fn(() => { throw new Error('network forbidden') })
    vi.stubGlobal('fetch', fetch)
    const { apiGet, apiPost } = await import('./api')
    expect(await apiGet('/auth/status')).toMatchObject({ authenticated: true, username: 'demo' })
    expect(await apiGet('/config/public')).toHaveProperty('app_name')
    await expect(apiPost('/admin/cookie', { cookie: 'placeholder' })).rejects.toThrow('演示模式')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('keeps real installations on the authenticated HTTP transport', async () => {
    vi.stubEnv('VITE_DEMO_MODE', 'false')
    vi.resetModules()
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ voice_connected: false })))
    vi.stubGlobal('fetch', fetch)
    const { apiGet } = await import('./api')
    expect(await apiGet('/voice/status')).toEqual({ voice_connected: false })
    expect(fetch).toHaveBeenCalledWith('/api/voice/status', expect.objectContaining({ credentials: 'include' }))
  })

  it('routes controls, uploads and assets to the selected server even with a legacy API base', async () => {
    vi.stubEnv('VITE_API_BASE', 'https://legacy.example/api')
    vi.stubGlobal('window', { location: { pathname: '/s/friends/queue' } })
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}')))
    vi.stubGlobal('fetch', fetch)
    const { apiGet, apiPut, apiPutFile, apiUrl } = await import('./api')
    const { setCsrfToken } = await import('./session')
    setCsrfToken('friends-csrf')
    await apiGet('/queue')
    await apiPut('/voice/volume', { volume: 35 })
    await apiPutFile('/admin/assets/teamspeak-avatar', new File(['image'], 'avatar.png', { type: 'image/png' }))
    expect(fetch.mock.calls.map(call => call[0])).toEqual([
      '/api/servers/friends/queue', '/api/servers/friends/voice/volume', '/api/servers/friends/admin/assets/teamspeak-avatar',
    ])
    expect(fetch.mock.calls[1][1].headers['X-CSRF-Token']).toBe('friends-csrf')
    expect(apiUrl('/assets/web-app-icon')).toBe('/api/servers/friends/assets/web-app-icon')
  })
})
