import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getNeteaseQualityLevel, NETEASE_QUALITY_STORAGE_KEY, setNeteaseQualityLevel } from './neteaseQuality'
import { buildNeteaseQueuePayload } from './queue'
import { getQQMusicQuality, qqmusicQualityPayload, setQQMusicQuality } from './qqmusicQuality'

beforeEach(() => {
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', { getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => store.set(key, value) })
})
afterEach(() => vi.unstubAllGlobals())

describe('provider quality preferences', () => {
  it('follows server for missing preferences and omits wire fields', () => {
    expect(getNeteaseQualityLevel()).toBe('server')
    expect(getQQMusicQuality()).toBe('server')
    expect(buildNeteaseQueuePayload({ id: 1 })).not.toHaveProperty('level')
    expect(qqmusicQualityPayload()).not.toHaveProperty('quality')
  })

  it('preserves old explicit Netease auto, independently of QQ', () => {
    localStorage.setItem(NETEASE_QUALITY_STORAGE_KEY, 'auto')
    setQQMusicQuality('128')
    expect(buildNeteaseQueuePayload({ id: 1 })).toHaveProperty('level', 'auto')
    expect(qqmusicQualityPayload()).toEqual({ quality: '128' })
    setNeteaseQualityLevel('standard')
    expect(getQQMusicQuality()).toBe('128')
    setNeteaseQualityLevel('server')
    expect(buildNeteaseQueuePayload({ id: 1 })).not.toHaveProperty('level')
  })

  it('keeps valid legacy preferences and discards unknown or cross-provider preferences', () => {
    for (const value of ['standard', 'hires', 'jymaster'] as const) {
      localStorage.setItem(NETEASE_QUALITY_STORAGE_KEY, value)
      expect(getNeteaseQualityLevel()).toBe(value)
    }
    expect(setNeteaseQualityLevel('320')).toBe('server')
    expect(setQQMusicQuality('lossless')).toBe('server')
  })
})
