export interface PlaybackRecoveryStatus {
  pending: boolean
  target_id?: number
  attempt?: number
  retry_count?: number
  phase?: 'starting' | 'retry' | 'cooldown'
  next_retry_at?: number
  last_reason?: string
}

export function recoveryMessage(status: PlaybackRecoveryStatus, now: number): string {
  if (!status.pending) return ''
  const target = status.target_id ? `歌曲 #${status.target_id}` : '播放队列'
  const seconds = Math.max(0, Math.ceil((status.next_retry_at ?? now / 1000) - now / 1000))
  const reasons: Record<string, string> = {
    network_timeout: '网络超时', network_error: '网络连接异常', rate_limited: '请求限流',
    upstream_unavailable: '音乐源暂不可用', upstream_risk: '平台风控',
  }
  const reason = reasons[status.last_reason ?? '']
  const suffix = reason ? ` · ${reason}` : ''
  if (status.phase === 'cooldown') return `${target} 暂时不可用，冷却 ${seconds} 秒后再试${suffix}`
  if (status.phase === 'starting') return `${target} 正在准备恢复播放${suffix}`
  return `${target} 将在 ${seconds} 秒后重试（${status.attempt ?? 0}/${status.retry_count ?? 0}）${suffix}`
}
