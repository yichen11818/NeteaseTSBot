import { apiPost } from '../api'

type ArtistLike = {
  name?: string
}

type AlbumLike = {
  name?: string
  picUrl?: string
  pic_url?: string
}

export type NeteaseTrackLike = {
  id: number | string
  name?: string
  ar?: ArtistLike[]
  artists?: ArtistLike[]
  al?: AlbumLike
  album?: AlbumLike | string
  dt?: number
  duration?: number
  picUrl?: string
  coverImgUrl?: string
}

export type BulkEnqueueResult = {
  addedCount: number
  failed: Array<{
    title: string
    message: string
  }>
}

type EnqueueNeteaseTracksOptions = {
  playFirst?: boolean
  onProgress?: (current: number, total: number, title: string) => void
}

function getTrackTitle(track: NeteaseTrackLike): string {
  return String(track?.name || track?.id || '未知歌曲')
}

function getTrackArtist(track: NeteaseTrackLike): string {
  return (track.ar || track.artists || []).map((artist) => artist.name || '').filter(Boolean).join(', ')
}

function getTrackAlbum(track: NeteaseTrackLike): string {
  if (track.al?.name) return track.al.name
  if (typeof track.album === 'string') return track.album
  if (track.album && typeof track.album === 'object' && track.album.name) return track.album.name
  return ''
}

function getTrackCoverUrl(track: NeteaseTrackLike): string {
  if (track.al?.picUrl) return track.al.picUrl
  if (track.al?.pic_url) return track.al.pic_url
  if (track.album && typeof track.album === 'object' && track.album.picUrl) return track.album.picUrl
  if (track.album && typeof track.album === 'object' && track.album.pic_url) return track.album.pic_url
  if (track.picUrl) return track.picUrl
  if (track.coverImgUrl) return track.coverImgUrl
  return ''
}

function getTrackDurationMs(track: NeteaseTrackLike): number | undefined {
  const raw = typeof track.dt === 'number' ? track.dt : track.duration
  return typeof raw === 'number' && Number.isFinite(raw) && raw > 0 ? raw : undefined
}

export function buildNeteaseQueuePayload(track: NeteaseTrackLike, playNow: boolean = false) {
  return {
    song_id: String(track.id),
    title: getTrackTitle(track),
    artist: getTrackArtist(track),
    album: getTrackAlbum(track),
    duration_ms: getTrackDurationMs(track),
    cover_url: getTrackCoverUrl(track),
    play_now: playNow,
  }
}

export async function enqueueNeteaseTracks(
  tracks: NeteaseTrackLike[],
  options: EnqueueNeteaseTracksOptions = {},
): Promise<BulkEnqueueResult> {
  const failed: BulkEnqueueResult['failed'] = []
  let addedCount = 0
  const total = tracks.length

  for (const [index, track] of tracks.entries()) {
    const title = getTrackTitle(track)
    options.onProgress?.(index + 1, total, title)

    try {
      await apiPost('/queue/netease', buildNeteaseQueuePayload(track, Boolean(options.playFirst && index === 0)))
      addedCount++
    } catch (e: any) {
      failed.push({
        title,
        message: String(e?.message ?? e),
      })
    }
  }

  return { addedCount, failed }
}


export function summarizeBulkEnqueueFailures(
  failed: BulkEnqueueResult['failed'],
  limit: number = 3,
): string {
  const preview = failed
    .slice(0, limit)
    .map((item) => `${item.title}：${item.message}`)
    .join('；')

  if (failed.length <= limit) {
    return preview
  }

  return `${preview} 等 ${failed.length} 首歌曲`
}
