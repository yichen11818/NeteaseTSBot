import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { readServerStorage, removeServerStorage, writeServerStorage } from './servers'

const COOKIE = 'tsbot_user_netease_cookie'
const HOME_COOKIE = `tsbot:server:home:${COOKIE}`

beforeEach(() => {
  const store = new Map([[COOKIE, 'legacy-cookie'], [HOME_COOKIE, 'home-cookie']])
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => store.set(key, value),
    removeItem: (key: string) => store.delete(key),
  })
  vi.stubGlobal('window', { location: { pathname: '/s/home/cookie' } })
})

afterEach(() => { vi.unstubAllGlobals(); vi.resetModules() })

it('retires a legacy cookie when the selected server already has an account', () => {
  expect(readServerStorage(COOKIE)).toBe('home-cookie')
  expect(localStorage.getItem(COOKIE)).toBeNull()
  window.location.pathname = '/s/friends/cookie'
  expect(readServerStorage(COOKIE)).toBe('')
})

it('clearing an account cannot resurrect it or migrate it to another server', () => {
  removeServerStorage(COOKIE)
  expect(readServerStorage(COOKIE)).toBe('')
  window.location.pathname = '/s/friends/cookie'
  expect(readServerStorage(COOKIE)).toBe('')
})

it('replacing an account retires legacy credentials while preserving other servers', () => {
  const friendsKey = `tsbot:server:friends:${COOKIE}`
  localStorage.setItem(friendsKey, 'friends-cookie')
  writeServerStorage(COOKIE, 'new-cookie')
  expect(readServerStorage(COOKIE)).toBe('new-cookie')
  expect(localStorage.getItem(COOKIE)).toBeNull()
  expect(localStorage.getItem(friendsKey)).toBe('friends-cookie')
})

it('preserves single-server read, write and clear behavior', () => {
  window.location.pathname = '/cookie'
  expect(readServerStorage(COOKIE)).toBe('legacy-cookie')
  writeServerStorage(COOKIE, 'single-cookie')
  expect(readServerStorage(COOKIE)).toBe('single-cookie')
  removeServerStorage(COOKIE)
  expect(readServerStorage(COOKIE)).toBe('')
  expect(localStorage.getItem(HOME_COOKIE)).toBe('home-cookie')
})

it('migrates cookies when loading likes before opening the account page', async () => {
  localStorage.removeItem(HOME_COOKIE)
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ songs: [], has_more: false })))
  vi.stubGlobal('fetch', fetch)
  const { useNeteaseLikes } = await import('./composables/useNeteaseLikes')
  const likes = useNeteaseLikes()
  await likes.load(true)
  expect(likes.error.value).toBe('')
  expect(fetch.mock.calls[0][1].headers['X-Netease-Cookie']).toBe('legacy-cookie')
  expect(localStorage.getItem(COOKIE)).toBeNull()
  expect(localStorage.getItem(HOME_COOKIE)).toBe('legacy-cookie')
})
