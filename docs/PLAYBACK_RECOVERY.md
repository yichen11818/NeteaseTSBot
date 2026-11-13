# 播放恢复 / Playback recovery

在控制台「配置 → 播放恢复」设置。策略存入现有配置数据库；环境变量仅用于首次初始化或恢复默认值。保存仅暂存，保存并应用后生效，无需重启 Voice。

| 配置 | 默认值 | 范围 / 语义 |
| --- | --- | --- |
| 自动恢复 | 开启 | 关闭并应用会立即取消等待，不中断正常播放 |
| 重试次数 | 3 | 0–10，首次请求之后的额外次数；0 直接执行耗尽策略 |
| 首次重试间隔 | 15 秒 | 5–300 秒 |
| 最大重试间隔 | 60 秒 | 5–3600 秒，不小于首次间隔；间隔指数递增至此上限 |
| 耗尽动作 | SKIP | SKIP 暂时跳过且保留条目；WAIT 保留目标，冷却后开始新一轮 |
| 冷却时间 | 300 秒 | 30–3600 秒 |
| 连续失败曲目上限 | 3 | 1–100，达到后先冷却，避免音乐源整体异常时快速请求整个队列 |

对应环境变量前缀为 `TSBOT_PLAYBACK_`，后缀依次为 `RECOVERY_ENABLED`、`RETRY_COUNT`、`RETRY_INITIAL_DELAY_SECONDS`、`RETRY_MAX_DELAY_SECONDS`、`EXHAUSTED_ACTION`、`COOLDOWN_SECONDS`、`FAILED_TRACKS_BEFORE_COOLDOWN`。一次恢复使用开始时的配置快照；更改策略影响后续恢复，显式关闭除外。

重试仅处理超时、网络连接故障、429、502/503/504 和已识别的网易云风控响应。认证、付费限制、歌曲不存在和程序错误不作为临时故障重试；原有不可播放条目的处理仍适用。恢复不能解除平台风控或账号权限限制。

手动选择队列中的具体歌曲时，首次失败返回该歌曲的错误，不删除目标或自动播放其他歌曲；原来正常播放的歌曲继续保留。首次失败属于临时故障时仍会安排恢复。自动续播则沿用不可播放条目的跳过处理。

B 站 API 与 yt-dlp 备用解析保留原始故障类别。认证/权限、业务拒绝、无效响应和未分类异常即使对外返回 502，也不会仅凭此状态码重试；只有明确的网络或临时上游故障进入恢复。主解析失败后仍可尝试备用解析；两条路径都失败时，已识别的永久或未分类故障优先阻止重试。

播放器显示目标队列编号、当前重试次数及倒计时。冷却时仍可按下一首或「停止并取消重试」。暂停、清空队列、新的播放目标与关闭后端都会取消旧任务。暂时跳过的条目保留在队列，后续一轮会再尝试。音质与请求人随目标保留。HTTP 请求首次播放失败仍返回错误，后台安排恢复不代表首次请求成功。

`GET /voice/status` 新增 `recovery`：非活动时为 `{"pending": false}`；等待时还包含 `target_id`、`attempt`、`retry_count`、`next_retry_at`（Unix 秒）、`phase`（`starting` / `retry` / `cooldown`）及 `last_reason` 分类。该对象不含签名地址、Cookie 或上游响应正文。`POST /voice/stop` 停止播放并取消等待，使用现有访问控制。

The console persists a provider-independent recovery policy. Retry counts are additional attempts after the initial failure. SKIP keeps the queue entry for a later pass; WAIT holds the target through cooldown. Policy updates apply to subsequent recovery runs, except disabling and applying cancels pending work immediately. Healthy playback is unaffected. Only classified transient failures are retried; recovery does not bypass provider restrictions. Stop, pause, clear, a new playback intent and shutdown cancel stale work. The status endpoint exposes safe scheduling metadata, and the initial HTTP error remains an error even when background recovery is arranged.
