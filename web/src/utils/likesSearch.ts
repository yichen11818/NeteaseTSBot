function getSongArtists(song: any): string {
  return ((song?.ar || song?.artists) || [])
    .map((artist: any) => artist?.name)
    .filter(Boolean)
    .join(', ')
}

function getSongAlbum(song: any): string {
  return String(song?.al?.name || song?.album?.name || '').trim()
}

export function filterLikedSongs(songs: any[], query: string): any[] {
  const normalizedQuery = query.trim().toLowerCase()
  if (!normalizedQuery) return songs

  return songs.filter((song) => {
    const title = String(song?.name || '').toLowerCase()
    const artist = getSongArtists(song).toLowerCase()
    const album = getSongAlbum(song).toLowerCase()
    return title.includes(normalizedQuery) || artist.includes(normalizedQuery) || album.includes(normalizedQuery)
  })
}
