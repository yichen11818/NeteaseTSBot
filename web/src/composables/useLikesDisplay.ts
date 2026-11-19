import { computed, ref, watch, type Ref } from 'vue'
import { filterLikedSongs } from '../utils/likesSearch'

export type LikesSortMode = 'default' | 'added' | 'name'

const PAGE_SIZE = 200
const LOAD_MORE_THRESHOLD_PX = 120

export function isNearLikesBottom(metrics: {
  scrollHeight: number
  scrollTop: number
  clientHeight: number
}): boolean {
  return metrics.scrollHeight - metrics.scrollTop - metrics.clientHeight <= LOAD_MORE_THRESHOLD_PX
}

export function useLikesDisplay(
  songs: Ref<any[]>,
  searchQuery: Ref<string>,
  sortMode: Ref<LikesSortMode>,
) {
  const displayedCount = ref(PAGE_SIZE)

  const sortedSongs = computed(() => {
    const list = [...songs.value]
    if (sortMode.value === 'added') {
      return list.sort((a, b) => Number(b?.added_at || 0) - Number(a?.added_at || 0))
    }
    if (sortMode.value === 'name') {
      return list.sort((a, b) =>
        String(a?.name || '').localeCompare(String(b?.name || ''), 'zh-CN', { numeric: true }),
      )
    }
    return list
  })

  const matchedSongs = computed(() => filterLikedSongs(sortedSongs.value, searchQuery.value))
  const visibleSongs = computed(() => matchedSongs.value.slice(0, displayedCount.value))
  const hasMore = computed(() => displayedCount.value < matchedSongs.value.length)

  watch([searchQuery, sortMode], () => {
    displayedCount.value = PAGE_SIZE
  }, { flush: 'sync' })

  return {
    visibleSongs,
    hasMore,
    loadMore: () => {
      displayedCount.value += PAGE_SIZE
    },
  }
}
