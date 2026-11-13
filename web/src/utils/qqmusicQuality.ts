export const QQMUSIC_QUALITY_STORAGE_KEY = 'tsbot:qqmusic:quality'
export const QQMUSIC_QUALITY_OPTIONS = [
  { value: 'server', label: '跟随服务器' },
  { value: 'm4a', label: 'M4A' },
  { value: '128', label: 'MP3 128' },
  { value: '320', label: 'MP3 320' },
] as const
export type QQMusicQuality = typeof QQMUSIC_QUALITY_OPTIONS[number]['value']

function normalize(value: unknown): QQMusicQuality {
  return QQMUSIC_QUALITY_OPTIONS.find(option => option.value === value)?.value ?? 'server'
}
export function getQQMusicQuality(): QQMusicQuality {
  return normalize(typeof localStorage === 'undefined' ? null : localStorage.getItem(QQMUSIC_QUALITY_STORAGE_KEY))
}
export function setQQMusicQuality(value: unknown): QQMusicQuality {
  const selected = normalize(value)
  if (typeof localStorage !== 'undefined') localStorage.setItem(QQMUSIC_QUALITY_STORAGE_KEY, selected)
  return selected
}
export function qqmusicQualityPayload(value = getQQMusicQuality()): { quality?: Exclude<QQMusicQuality, 'server'> } {
  return value === 'server' ? {} : { quality: value }
}
