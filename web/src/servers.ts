import { DEMO_MODE } from './demoMode'

export interface ServerEntry {
  readonly id: string
  readonly name: string
}

const SERVER_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/

export function serverIdFromPath(path: string): string {
  if (!path.startsWith('/s/')) return ''
  const id = path.split('/')[2]
  if (!SERVER_ID.test(id)) throw new Error('服务器链接无效，请从服务器列表重新选择')
  return id
}

export function currentServerId(): string {
  return typeof window === 'undefined' || DEMO_MODE ? '' : serverIdFromPath(window.location.pathname)
}

export function serverPageUrl(id: string): string {
  if (!SERVER_ID.test(id)) throw new Error('无效的服务器 ID')
  return `/s/${id}/search`
}

export function routerBase(): string {
  const id = currentServerId()
  return id ? `/s/${id}/` : import.meta.env.BASE_URL
}

export function serverStorageKey(key: string): string {
  const id = currentServerId()
  return id ? `tsbot:server:${id}:${key}` : key
}

export function readServerStorage(key: string): string {
  const scopedKey = serverStorageKey(key)
  const current = localStorage.getItem(scopedKey)
  if (current !== null) return current
  if (scopedKey === key) return ''

  const legacy = localStorage.getItem(key)
  if (legacy === null) return ''
  localStorage.setItem(scopedKey, legacy)
  localStorage.removeItem(key)
  return legacy
}

export function writeServerStorage(key: string, value: string): void {
  localStorage.setItem(serverStorageKey(key), value)
}

export function removeServerStorage(key: string): void {
  localStorage.removeItem(serverStorageKey(key))
}

export function parseServerCatalog(value: unknown): readonly ServerEntry[] {
  const list = (value as { servers?: unknown } | null)?.servers
  if (!Array.isArray(list)) throw new Error('服务器清单格式错误：缺少 servers 数组')
  const servers = list.map((entry: unknown): ServerEntry => {
    const item = entry as Partial<ServerEntry> | null
    if (!item || typeof item.id !== 'string' || !SERVER_ID.test(item.id)
      || typeof item.name !== 'string' || !item.name.trim()) {
      throw new Error('服务器清单中存在无效的 ID 或名称')
    }
    return Object.freeze({ id: item.id, name: item.name.trim() })
  })
  if (new Set(servers.map(server => server.id)).size !== servers.length) {
    throw new Error('服务器清单中存在重复的 ID')
  }
  return Object.freeze(servers)
}

export async function loadServerCatalog(): Promise<readonly ServerEntry[]> {
  if (DEMO_MODE) return []
  const response = await fetch(`${import.meta.env.BASE_URL}servers.json`, { cache: 'no-store' })
  if (!response.ok) throw new Error(`无法读取服务器清单（HTTP ${response.status}）`)
  return parseServerCatalog(await response.json())
}

export function validateServerSelection(servers: readonly ServerEntry[]): void {
  const id = currentServerId()
  if (id && !servers.some(server => server.id === id)) {
    throw new Error(`服务器 ${id} 不在当前清单中，请选择其他服务器`)
  }
}
