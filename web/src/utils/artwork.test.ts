import { describe, expect, it } from 'vitest'
import { artworkUrl } from './artwork'

describe('cover URLs', () => {
  it('upgrades Bilibili covers from old results and saved favorites without changing image transforms', () => {
    expect(artworkUrl(' http://i0.hdslb.com/bfs/archive/cover.jpg@320w_200h.webp '))
      .toBe('https://i0.hdslb.com/bfs/archive/cover.jpg@320w_200h.webp')
    expect(artworkUrl('//i2.hdslb.com/bfs/archive/cover.jpg')).toBe('https://i2.hdslb.com/bfs/archive/cover.jpg')
    expect(artworkUrl('https://i1.hdslb.com/bfs/archive/cover.jpg')).toBe('https://i1.hdslb.com/bfs/archive/cover.jpg')
  })

  it('preserves demo assets and other providers', () => {
    for (const url of ['/NeteaseTSBot/demo-cover.svg', 'https://p1.music.126.net/cover.jpg?param=100y100', 'http://example.com/hdslb.com.jpg']) {
      expect(artworkUrl(url)).toBe(url)
    }
    expect(artworkUrl(null)).toBe('')
  })
})
