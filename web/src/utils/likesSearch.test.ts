import { describe, expect, it } from 'vitest'
import { filterLikedSongs } from './likesSearch'

describe('liked song search', () => {
  const songs = [
    { id: 1, name: '晴天', ar: [{ name: '周杰伦' }], al: { name: '叶惠美' } },
    { id: 2, name: 'The Weekend', artists: [{ name: 'SZA' }], album: { name: 'Ctrl' } },
  ]

  it('matches title, artist or album without case and surrounding whitespace', () => {
    expect(filterLikedSongs(songs, ' 晴天 ')).toEqual([songs[0]])
    expect(filterLikedSongs(songs, '周杰伦')).toEqual([songs[0]])
    expect(filterLikedSongs(songs, '叶惠美')).toEqual([songs[0]])
    expect(filterLikedSongs(songs, 'weekend')).toEqual([songs[1]])
    expect(filterLikedSongs(songs, 'sza')).toEqual([songs[1]])
    expect(filterLikedSongs(songs, 'ctrl')).toEqual([songs[1]])
  })

  it('returns no songs when the query does not match', () => {
    expect(filterLikedSongs(songs, '不存在')).toEqual([])
  })
})
