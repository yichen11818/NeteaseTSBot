import { ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { isNearLikesBottom, useLikesDisplay } from './useLikesDisplay'

function makeSongs(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    id: index + 1,
    name: `曲目${String(index).padStart(3, '0')}`,
    added_at: index,
  }))
}

describe('liked songs display', () => {
  it('shows the first 200 songs and reveals another 200 each time', () => {
    const songs = ref(makeSongs(450))
    const query = ref('')
    const sortMode = ref<'default' | 'added' | 'name'>('default')
    const display = useLikesDisplay(songs, query, sortMode)

    expect(display.visibleSongs.value).toHaveLength(200)
    expect(display.visibleSongs.value[0].id).toBe(1)
    expect(display.visibleSongs.value[199].id).toBe(200)
    expect(display.hasMore.value).toBe(true)

    display.loadMore()

    expect(display.visibleSongs.value).toHaveLength(400)
    expect(display.visibleSongs.value[399].id).toBe(400)

    display.loadMore()

    expect(display.visibleSongs.value).toHaveLength(450)
    expect(display.hasMore.value).toBe(false)
  })

  it('sorts the complete collection before limiting the page', () => {
    const songs = ref(makeSongs(250))
    const query = ref('')
    const sortMode = ref<'default' | 'added' | 'name'>('default')
    const display = useLikesDisplay(songs, query, sortMode)

    sortMode.value = 'added'

    expect(display.visibleSongs.value[0].id).toBe(250)
    expect(display.visibleSongs.value[199].id).toBe(51)
  })

  it('sorts the complete collection by name before limiting the page', () => {
    const songs = ref(makeSongs(250).map((song) => ({
      ...song,
      name: `曲目${String(250 - song.id).padStart(3, '0')}`,
    })))
    const query = ref('')
    const sortMode = ref<'default' | 'added' | 'name'>('default')
    const display = useLikesDisplay(songs, query, sortMode)

    sortMode.value = 'name'

    expect(display.visibleSongs.value[0].id).toBe(250)
    expect(display.visibleSongs.value[199].id).toBe(51)
  })

  it('searches the complete collection before limiting the results', () => {
    const songs = ref(makeSongs(250))
    const query = ref('曲目249')
    const sortMode = ref<'default' | 'added' | 'name'>('default')
    const display = useLikesDisplay(songs, query, sortMode)

    expect(display.visibleSongs.value).toEqual([songs.value[249]])
  })

  it('resets to 200 results when the sort changes', () => {
    const songs = ref(makeSongs(450))
    const query = ref('')
    const sortMode = ref<'default' | 'added' | 'name'>('default')
    const display = useLikesDisplay(songs, query, sortMode)

    display.loadMore()
    sortMode.value = 'name'

    expect(display.visibleSongs.value).toHaveLength(200)
  })

  it('resets to 200 results when the search changes', () => {
    const songs = ref(makeSongs(450))
    const query = ref('')
    const sortMode = ref<'default' | 'added' | 'name'>('default')
    const display = useLikesDisplay(songs, query, sortMode)

    display.loadMore()
    query.value = '曲目'

    expect(display.visibleSongs.value).toHaveLength(200)
  })
})

describe('liked songs automatic loading', () => {
  it('loads when the scroll position is within 120px of the bottom', () => {
    expect(isNearLikesBottom({ scrollHeight: 2000, scrollTop: 1280, clientHeight: 600 })).toBe(true)
  })

  it('does not load when the scroll position is more than 120px from the bottom', () => {
    expect(isNearLikesBottom({ scrollHeight: 2000, scrollTop: 1279, clientHeight: 600 })).toBe(false)
  })
})
