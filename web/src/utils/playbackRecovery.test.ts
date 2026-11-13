import { describe, expect, it } from 'vitest'
import { recoveryMessage } from './playbackRecovery'

describe('playback recovery status', () => {
  it('shows target, bounded retry count and the next attempt', () => {
    expect(recoveryMessage({ pending: true, target_id: 20, attempt: 2, retry_count: 3,
      phase: 'retry', next_retry_at: 115 }, 100_000)).toBe('歌曲 #20 将在 15 秒后重试（2/3）')
  })

  it('distinguishes cooldown from retries and hides inactive state', () => {
    expect(recoveryMessage({ pending: true, target_id: 20, phase: 'cooldown', next_retry_at: 400 }, 100_000))
      .toBe('歌曲 #20 暂时不可用，冷却 300 秒后再试')
    expect(recoveryMessage({ pending: false }, 0)).toBe('')
  })
})
