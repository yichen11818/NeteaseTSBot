type NeteaseArtist = { name: string }

type NeteaseAlbum = {
  name?: string
  picUrl?: string
}

export type FavoriteSong = {
  id: number
  name: string
  ar?: NeteaseArtist[]
  al?: NeteaseAlbum
  dt?: number
  _fav_at?: number
}

export type FavoritePlaylist = {
  id: number
  name: string
  coverImgUrl?: string
  picUrl?: string
  playCount?: number
  creator?: { nickname?: string }
  _fav_at?: number
}

const SONGS_KEY = 'tsbot:fav:songs'
const PLAYLISTS_KEY = 'tsbot:fav:playlists'

function safeParseJson<T>(raw: string | null, fallback: T): T {
  if (!raw) return fallback
  try {
    const obj = JSON.parse(raw)
    return (obj as T) ?? fallback
  } catch {
    return fallback
  }
}

function normalizeSong(input: any): FavoriteSong | null {
  const id = Number(input?.id)
  if (!Number.isFinite(id) || id <= 0) return null

  const name = String(input?.name || input?.title || '').trim()
  if (!name) return null

  const arRaw = input?.ar || input?.artists
  const ar: NeteaseArtist[] | undefined = Array.isArray(arRaw)
    ? arRaw
        .map((a: any) => ({ name: String(a?.name || '').trim() }))
        .filter((a: any) => a.name)
    : undefined

  const alRaw = input?.al || input?.album
  const al: NeteaseAlbum | undefined = alRaw
    ? {
        name: alRaw?.name ? String(alRaw.name) : undefined,
        picUrl: alRaw?.picUrl ? String(alRaw.picUrl) : (alRaw?.pic_url ? String(alRaw.pic_url) : undefined),
      }
    : undefined

  const dt = input?.dt ?? input?.duration
  const dtMs = Number(dt)

  return {
    id,
    name,
    ar,
    al,
    dt: Number.isFinite(dtMs) && dtMs > 0 ? dtMs : undefined,
  }
}

function normalizePlaylist(input: any): FavoritePlaylist | null {
  const id = Number(input?.id)
  if (!Number.isFinite(id) || id <= 0) return null

  const name = String(input?.name || '').trim()
  if (!name) return null

  const coverImgUrl = input?.coverImgUrl ? String(input.coverImgUrl) : undefined
  const picUrl = input?.picUrl ? String(input.picUrl) : undefined
  const playCount = Number(input?.playCount)

  const creator = input?.creator && typeof input.creator === 'object'
    ? { nickname: input.creator.nickname ? String(input.creator.nickname) : undefined }
    : undefined

  return {
    id,
    name,
    coverImgUrl,
    picUrl,
    playCount: Number.isFinite(playCount) ? playCount : undefined,
    creator,
  }
}

export function getFavoriteSongs(): FavoriteSong[] {
  const raw = localStorage.getItem(SONGS_KEY)
  const arr = safeParseJson<any[]>(raw, [])
  if (!Array.isArray(arr)) return []
  return arr.filter(Boolean)
}

export function isFavoriteSong(songId: number | string): boolean {
  const id = Number(songId)
  if (!Number.isFinite(id) || id <= 0) return false
  return getFavoriteSongs().some((s) => Number(s?.id) === id)
}

export function toggleFavoriteSong(songLike: any): boolean {
  const song = normalizeSong(songLike)
  if (!song) return false

  const list = getFavoriteSongs()
  const idx = list.findIndex((s) => Number(s?.id) === song.id)

  if (idx >= 0) {
    list.splice(idx, 1)
    localStorage.setItem(SONGS_KEY, JSON.stringify(list))
    return false
  }

  const now = Date.now()
  const next: FavoriteSong = { ...song, _fav_at: now }
  const out = [next, ...list]
  localStorage.setItem(SONGS_KEY, JSON.stringify(out))
  return true
}

export function removeFavoriteSong(songId: number | string): void {
  const id = Number(songId)
  if (!Number.isFinite(id) || id <= 0) return
  const list = getFavoriteSongs().filter((s) => Number(s?.id) !== id)
  localStorage.setItem(SONGS_KEY, JSON.stringify(list))
}

export function getFavoritePlaylists(): FavoritePlaylist[] {
  const raw = localStorage.getItem(PLAYLISTS_KEY)
  const arr = safeParseJson<any[]>(raw, [])
  if (!Array.isArray(arr)) return []
  return arr.filter(Boolean)
}

export function isFavoritePlaylist(playlistId: number | string): boolean {
  const id = Number(playlistId)
  if (!Number.isFinite(id) || id <= 0) return false
  return getFavoritePlaylists().some((p) => Number(p?.id) === id)
}

export function toggleFavoritePlaylist(playlistLike: any): boolean {
  const pl = normalizePlaylist(playlistLike)
  if (!pl) return false

  const list = getFavoritePlaylists()
  const idx = list.findIndex((p) => Number(p?.id) === pl.id)

  if (idx >= 0) {
    list.splice(idx, 1)
    localStorage.setItem(PLAYLISTS_KEY, JSON.stringify(list))
    return false
  }

  const now = Date.now()
  const next: FavoritePlaylist = { ...pl, _fav_at: now }
  const out = [next, ...list]
  localStorage.setItem(PLAYLISTS_KEY, JSON.stringify(out))
  return true
}

export function removeFavoritePlaylist(playlistId: number | string): void {
  const id = Number(playlistId)
  if (!Number.isFinite(id) || id <= 0) return
  const list = getFavoritePlaylists().filter((p) => Number(p?.id) !== id)
  localStorage.setItem(PLAYLISTS_KEY, JSON.stringify(list))
}
