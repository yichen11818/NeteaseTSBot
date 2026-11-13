export const NETEASE_QUALITY_STORAGE_KEY = 'tsbot:netease:quality'

export const NETEASE_QUALITY_OPTIONS = [
  { value: 'server', label: '跟随服务器' },
  { value: 'auto', label: '自动最高' },
  { value: 'standard', label: '标准' },
  { value: 'higher', label: '较高' },
  { value: 'exhigh', label: '极高' },
  { value: 'lossless', label: '无损' },
  { value: 'hires', label: 'Hi-Res' },
  { value: 'jyeffect', label: '高清环绕声' },
  { value: 'sky', label: '沉浸环绕声' },
  { value: 'dolby', label: '杜比全景声' },
  { value: 'jymaster', label: '超清母带' },
] as const

export type NeteaseQualityLevel = typeof NETEASE_QUALITY_OPTIONS[number]['value']

const NETEASE_QUALITY_VALUES = new Set<string>(NETEASE_QUALITY_OPTIONS.map((option) => option.value))

export function normalizeNeteaseQualityLevel(value: unknown): NeteaseQualityLevel {
  const raw = String(value ?? '').trim().toLowerCase()
  if (NETEASE_QUALITY_VALUES.has(raw)) {
    return raw as NeteaseQualityLevel
  }
  return 'server'
}

export function getNeteaseQualityLevel(): NeteaseQualityLevel {
  if (typeof localStorage === 'undefined') {
    return 'server'
  }
  return normalizeNeteaseQualityLevel(localStorage.getItem(NETEASE_QUALITY_STORAGE_KEY))
}

export function setNeteaseQualityLevel(value: unknown): NeteaseQualityLevel {
  const normalized = normalizeNeteaseQualityLevel(value)
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(NETEASE_QUALITY_STORAGE_KEY, normalized)
  }
  return normalized
}

export function getNeteaseQualityLabel(value: unknown): string {
  const normalized = normalizeNeteaseQualityLevel(value)
  return NETEASE_QUALITY_OPTIONS.find((option) => option.value === normalized)?.label || '跟随服务器'
}

export function neteaseQualityPayload(value = getNeteaseQualityLevel()): { level?: Exclude<NeteaseQualityLevel, 'server'> } {
  return value === 'server' ? {} : { level: value }
}
