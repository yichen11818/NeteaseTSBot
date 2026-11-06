# TSBot Backend API 文档

这份文档面向需要直接调用 TSBot 后端的开发者，补充说明项目里的接口分组、鉴权方式、请求体字段、常见返回结构和调用示例。

如果本文档和运行中的 FastAPI OpenAPI 文档不一致，以运行中的 OpenAPI 为准：

- `http://127.0.0.1:8009/docs`
- `http://127.0.0.1:8009/openapi.json`

## 1. 基本信息

- 默认后端地址：`http://127.0.0.1:8009`
- 如果通过前端同源代理访问，通常走 `/api/*`
- 返回格式：除少数上游透传接口外，基本都返回 JSON
- 常见错误格式：`{"detail":"..."}` 或 `{"message":"..."}`

## 2. 鉴权与请求头

### 2.1 API Token

如果配置了以下任一环境变量：

- `TSBOT_API_TOKEN`
- `TSBOT_API_TOKENS`

那么所有非 `/admin/*` 接口都需要携带 API Token。

支持两种请求头写法：

```http
Authorization: Bearer <token>
```

或：

```http
x-api-token: <token>
```

不会要求 API Token 的路径：

- `/docs`
- `/redoc`
- `/openapi.json`
- `/admin/*`

### 2.2 Admin Token

部分管理员接口会校验 `TSBOT_ADMIN_TOKEN`。请求头格式：

```http
x-admin-token: <TSBOT_ADMIN_TOKEN>
```

注意：

- `/admin/status` 不校验 admin token，只用于检查网易云管理员 cookie 是否已设置
- 大部分其他 `/admin/*` 接口都需要 admin token

### 2.3 网易云用户 Cookie

部分网易云用户态接口需要在请求头里传入用户 cookie：

```http
x-netease-cookie: <cookie字符串>
```

适用接口包括：

- `/netease/account`
- `/netease/likelist`
- `/netease/likes`
- `/netease/playlists`
- `/playlist/detail` 可选携带，用于访问更完整的歌单信息

## 3. 数据结构约定

### 3.1 QueueItem

用于 `/queue`、`/external/queue`、`/external/status.queue_preview` 等返回。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | integer | 队列项 ID |
| `track_id` | string | 媒体标识，例如 `netease:123456`、`qqmusic:003abc` |
| `source` | string | 统一来源标识，例如 `netease`、`qqmusic`、`bilibili` |
| `song_id` | string | 网易云歌曲 ID，仅 `netease` 时返回 |
| `song_mid` | string | QQ 音乐歌曲 MID，仅 `qqmusic` 时返回 |
| `video_id` | string | B 站视频 ID，仅 `bilibili` 时返回 |
| `webpage_url` | string | 原始视频页，仅 `bilibili` 时返回 |
| `title` | string | 标题 |
| `artist` | string | 艺术家 |
| `album` | string | 专辑名 |
| `duration` | number \| null | 时长，单位秒 |
| `artwork` | string | 封面图 URL |
| `source_url` | string | 实际音频播放地址 |

### 3.2 HistoryItem

用于 `/history`、`/external/history` 返回。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | integer | 历史记录 ID |
| `played_at` | string | ISO 8601 时间 |
| `track_id` | string | 媒体标识 |
| `source` | string | 统一来源标识 |
| `song_id` | string | 网易云歌曲 ID，仅 `netease` 时返回 |
| `song_mid` | string | QQ 音乐歌曲 MID，仅 `qqmusic` 时返回 |
| `video_id` | string | B 站视频 ID，仅 `bilibili` 时返回 |
| `webpage_url` | string | 原始视频页，仅 `bilibili` 时返回 |
| `title` | string | 标题 |
| `artist` | string | 艺术家 |
| `album` | string | 专辑名 |
| `duration` | number \| null | 时长，单位秒 |
| `artwork` | string | 封面图 URL |
| `source_url` | string | 实际播放 URL |
| `requested_by` | string | 请求来源，例如 `web`、`external_api`、聊天点歌者昵称 |

### 3.3 LyricsResponse

用于 `/lyrics/{queue_item_id}` 返回。

```json
{
  "lyrics": [
    { "time": 12.34, "text": "歌词内容" }
  ]
}
```

### 3.4 时间和时长单位

这个项目里时长字段有两套单位，接入时要特别留意：

- 请求体里的 `duration_ms` 是毫秒
- 队列、历史、播放状态返回里的 `duration` 和 `current_time` 是秒

## 4. 推荐给外部系统使用的接口

`/external/*` 是推荐给外部机器人、面板、脚本集成的一组稳定接口，尽量避免第三方直接依赖前端内部用的细碎路由。

### 4.1 接口总览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/external/status` | 获取播放状态和队列预览 |
| `GET` | `/external/search` | 统一搜索网易云、QQ 音乐或 B 站视频 |
| `POST` | `/external/queue` | 根据 ID 或关键词加入队列，可选立即播放 |
| `GET` | `/external/queue` | 获取队列 |
| `DELETE` | `/external/queue` | 清空队列并尝试停止播放 |
| `DELETE` | `/external/queue/{item_id}` | 删除单个队列项 |
| `POST` | `/external/queue/{item_id}/play` | 播放指定队列项 |
| `GET` | `/external/history` | 获取历史播放记录 |
| `POST` | `/external/history/{history_id}/replay` | 通过历史记录重新加入队列或立即播放 |
| `POST` | `/external/player/action` | 播放、暂停、切歌等控制 |
| `PUT` | `/external/player/volume` | 设置音量 |
| `POST` | `/external/player/shuffle` | 开关随机播放 |
| `POST` | `/external/player/repeat` | 设置循环模式 |

### 4.2 `GET /external/status`

返回播放状态，以及前 10 项队列预览。

示例响应：

```json
{
  "state": "playing",
  "now_playing_title": "稻香",
  "now_playing_source_url": "https://...",
  "now_playing_artist": "周杰伦",
  "now_playing_album": "魔杰座",
  "artwork_url": "https://...",
  "track_id": 42,
  "current_time": 35.2,
  "duration": 223.4,
  "volume_percent": 100,
  "is_shuffled": false,
  "repeat_mode": "none",
  "queue_length": 5,
  "queue_preview": []
}
```

说明：

- 这里的 `track_id` 实际上是“当前播放的队列项 ID”，不是媒体字符串 `track_id`
- `repeat_mode` 取值：`none`、`all`、`one`

### 4.3 `GET /external/search`

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `keywords` | string | 是 | 搜索关键词 |
| `source` | string | 否 | `netease`、`qqmusic` 或 `bilibili`，默认 `netease` |
| `limit` | integer | 否 | 默认 `20`，最大 `50` |
| `page` | integer | 否 | 页码，从 `1` 开始 |

网易云示例：

```bash
curl -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8009/external/search?source=netease&keywords=周杰伦"
```

QQ 音乐示例：

```bash
curl -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8009/external/search?source=qqmusic&keywords=林俊杰"
```

B 站示例：

```bash
curl -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8009/external/search?source=bilibili&keywords=周杰伦"
```

统一返回结构：

```json
{
  "source": "netease",
  "keywords": "周杰伦",
  "page": 1,
  "limit": 20,
  "total": 123,
  "has_more": true,
  "items": [
    {
      "source": "netease",
      "track_id": "netease:123456",
      "song_id": "123456",
      "title": "稻香",
      "artist": "周杰伦",
      "album": "魔杰座",
      "duration_ms": 223000,
      "artwork_url": "https://..."
    }
  ]
}
```

QQ 音乐 `items` 里会使用 `song_mid` / `album_mid` 字段。

B 站 `items` 里会使用 `video_id` / `webpage_url` 字段。

当 `source=bilibili` 时，返回项还会尽量补充：

- `description`：视频简介摘要
- `likes`：点赞数
- `favorites`：收藏数
- `coins`：投币数

### 4.4 `POST /external/queue`

用于外部点歌。支持两种模式：

- 直接传具体歌曲 ID
- 只传关键词，让后端自动取首个搜索结果

请求体字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `source` | string | 否 | `netease`、`qqmusic` 或 `bilibili`，默认 `netease` |
| `keywords` | string | 否 | 按关键词自动搜索第一条 |
| `song_id` | string | 否 | 网易云歌曲 ID |
| `song_mid` | string | 否 | QQ 音乐歌曲 MID |
| `video_id` | string | 否 | B 站视频 BV 号或 av 号 |
| `title` | string | 否 | 标题，可不传，后端尽量补全 |
| `artist` | string | 否 | 艺术家，可不传 |
| `album` | string | 否 | 专辑名，可不传 |
| `album_mid` | string | 否 | QQ 音乐专辑 MID |
| `duration_ms` | integer | 否 | 毫秒 |
| `cover_url` | string | 否 | 封面图 URL |
| `level` | string | 否 | 网易云音质等级，默认 `auto` |
| `quality` | string | 否 | QQ 音乐音质，默认 `320` |
| `play_now` | boolean | 否 | 是否立即播放，默认 `false` |

注意：

- 网易云至少需要 `song_id` 或 `keywords` 之一
- QQ 音乐至少需要 `song_mid` 或 `keywords` 之一
- B 站至少需要 `video_id` 或 `keywords` 之一
- 网易云 `level` 支持：`auto`、`standard`、`higher`、`exhigh`、`lossless`、`hires`、`jyeffect`、`sky`、`dolby`、`jymaster`
- QQ 音乐实际入队和播放依赖服务端已配置管理员 QQ 音乐 cookie
- B 站播放时会由后端下载音频到本地缓存后，再交给 `voice-service` 播放

按关键词直接播放示例：

```bash
curl -X POST "http://127.0.0.1:8009/external/queue" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "netease",
    "keywords": "稻香",
    "level": "lossless",
    "play_now": true
  }'
```

按 QQ 音乐 MID 入队示例：

```bash
curl -X POST "http://127.0.0.1:8009/external/queue" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "qqmusic",
    "song_mid": "003aAYrm3GE0Ac",
    "title": "江南",
    "artist": "林俊杰",
    "album_mid": "001fNHEf1SFEFN",
    "play_now": false
  }'
```

按 B 站视频立即播放示例：

```bash
curl -X POST "http://127.0.0.1:8009/external/queue" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "bilibili",
    "video_id": "BV1QQSDBWEGn",
    "title": "【HiRes无损】周杰伦-太阳之子整张专辑 含歌词和单曲 共13首",
    "artist": "太阳之子周杰伦专辑",
    "play_now": true
  }'
```

示例响应：

```json
{
  "ok": true,
  "source": "netease",
  "queue_id": 88,
  "trial": false,
  "play_now": true,
  "track": {
    "source": "netease",
    "track_id": "netease:123456",
    "song_id": "123456",
    "title": "稻香",
    "artist": "周杰伦",
    "album": "魔杰座",
    "duration_ms": 223000,
    "artwork_url": "https://..."
  }
}
```

### 4.5 `GET /external/queue`

返回：

```json
{
  "count": 2,
  "items": []
}
```

`items` 的元素结构见“QueueItem”。

### 4.6 `DELETE /external/queue`

清空队列，并尝试停止当前播放。

示例响应：

```json
{
  "ok": true,
  "removed_count": 5,
  "playback_stopped": true
}
```

### 4.7 `DELETE /external/queue/{item_id}`

删除单个队列项。

### 4.8 `POST /external/queue/{item_id}/play`

播放已有的某个队列项。

### 4.9 `GET /external/history`

返回最近 200 条历史记录：

```json
{
  "count": 200,
  "items": []
}
```

`items` 的元素结构见“HistoryItem”。

### 4.10 `POST /external/history/{history_id}/replay`

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `play_now` | boolean | 否 | 默认 `true`；`false` 时只加入队列不立即播放 |

说明：

- 会根据历史项的 `track_id` 自动识别来源
- 目前支持 `netease:*`、`qqmusic:*`、`bilibili:*`
- 网易云和 QQ 音乐会重新获取最新播放地址
- B 站会重新解析视频信息，并在需要时重新准备本地缓存音频

### 4.11 `POST /external/player/action`

请求体：

```json
{
  "action": "next"
}
```

支持值：

- `play`
- `pause`
- `next`
- `previous`
- `skip`
- `resume`，等价于 `play`
- `continue`，等价于 `play`
- `switch`，等价于 `next`

说明：

- `next` 切到下一首；`all` / `one` 循环模式保留当前队列项，`none` 模式删除当前队列项。手动切歌不受单曲循环限制。
- `skip` 在所有模式下都会删除当前正在播放或加载的队列项，再自动播放下一首。
- `previous` 选择队列中仍保留的上一首；列表循环允许从第一首回到最后一首。已删除的曲目可通过历史重播接口重新加入。

### 4.12 `PUT /external/player/volume`

请求体：

```json
{
  "volume_percent": 120
}
```

范围会被后端强制裁剪到 `0..200`。

### 4.13 `POST /external/player/shuffle`

请求体：

```json
{
  "enabled": true
}
```

### 4.14 `POST /external/player/repeat`

请求体：

```json
{
  "mode": "all"
}
```

支持值：

- `none`
- `all`
- `one`

自然播放结束时，`none` 删除已播放条目并继续，队列耗尽后停止；`all` 保留条目并在末尾回到第一首；`one` 保留并重新播放当前条目。随机开关与循环模式独立：随机 + `all` 循环整个随机队列，随机 + `one` 仍重复当前歌曲。

单曲循环的当前条目被手动删除后，播放结束会继续下一首。明确不可播放的条目（如歌曲下架、无版权）会被跳过并删除，临时接口故障则保留队列供重试。

## 5. 播放控制接口 `/voice/*`

这组接口是现有 Web 控制台使用的原始播放控制接口，外部接入也可以用，但新的第三方集成更推荐使用 `/external/*`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/voice/status` | 获取播放状态 |
| `PUT` | `/voice/volume` | 设置音量 |
| `GET` | `/voice/fx` | 获取音效参数 |
| `PUT` | `/voice/fx` | 设置音效参数 |
| `POST` | `/voice/play` | 开始播放或从暂停恢复 |
| `POST` | `/voice/pause` | 暂停 |
| `POST` | `/voice/next` | 下一首 |
| `POST` | `/voice/skip` | 跳过当前曲目并删除队列项 |
| `POST` | `/voice/previous` | 上一首 |
| `POST` | `/voice/seek` | 调整当前播放进度 |
| `POST` | `/voice/shuffle` | 随机播放开关 |
| `POST` | `/voice/repeat` | 循环模式 |

### 5.1 `GET /voice/status`

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `state` | string | `idle`、`playing`、`paused`、`buffering`、`error` |
| `now_playing_title` | string | 当前播放标题 |
| `now_playing_source_url` | string | 当前源地址 |
| `now_playing_artist` | string | 当前艺术家 |
| `now_playing_album` | string | 当前专辑 |
| `artwork_url` | string | 当前封面 |
| `track_id` | integer \| null | 当前队列项 ID |
| `current_time` | number | 当前进度，秒 |
| `duration` | number | 总时长，秒 |
| `volume_percent` | integer | 音量百分比 |
| `is_shuffled` | boolean | 是否启用随机 |
| `repeat_mode` | string | `none`、`all`、`one` |

### 5.2 `PUT /voice/fx`

请求体字段都可选：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `pan` | number | 声像 |
| `width` | number | 声场宽度 |
| `swap_lr` | boolean | 左右声道互换 |
| `bass_db` | number | 低频增益 |
| `reverb_mix` | number | 混响比例 |

### 5.3 `POST /voice/seek`

请求体：

```json
{
  "time": 120.0
}
```

成功响应示例：

```json
{
  "ok": true,
  "time": 120.0
}
```

说明：

- `time` 单位为秒
- 如果后端已知当前曲目的总时长，会自动将目标进度限制在 `0 ~ duration`
- 对网易云和 QQ 音乐都会通过 `voice-service` 重新从对应偏移启动解码

## 6. 队列与历史接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/queue/netease` | 网易云歌曲入队 |
| `POST` | `/queue/qqmusic` | QQ 音乐歌曲入队 |
| `POST` | `/queue/bilibili` | B 站视频入队并在播放时下载音频 |
| `GET` | `/queue` | 获取队列 |
| `DELETE` | `/queue` | 清空队列 |
| `POST` | `/queue` | 通用低层入队 |
| `DELETE` | `/queue/{item_id}` | 删除队列项 |
| `POST` | `/queue/{item_id}/play` | 播放队列项 |
| `GET` | `/history` | 获取历史 |
| `POST` | `/history/{history_id}/replay` | 通过历史记录重新点歌 |

### 6.1 `POST /queue/netease`

请求体：

```json
{
    "song_id": "123456",
    "title": "稻香",
    "artist": "周杰伦",
    "album": "魔杰座",
    "duration_ms": 223000,
    "cover_url": "https://...",
    "level": "lossless",
    "play_now": true
}
```

说明：

- `level` 默认为 `auto`
- `auto` 会优先请求尽可能高的可播放音质
- `auto` 遇到网易云风控错误 `code=-460` 时，仅回退请求一次 `standard`；若仍被拒绝则返回明确错误，不持续重试
- 显式指定音质时不自动降级；风控错误返回 HTTP 503，其他上游 HTTP 错误返回 HTTP 502
- 指定更高音质时，上游 `/song/url/v1` 会按歌曲和账号能力返回实际可用的 `level` / `br`

响应：

```json
{
  "ok": true,
  "id": 123,
  "trial": false
}
```

### 6.2 `POST /queue/qqmusic`

请求体：

```json
{
  "song_mid": "003aAYrm3GE0Ac",
  "title": "江南",
  "artist": "林俊杰",
  "play_now": true,
  "quality": "320",
  "album_mid": "001fNHEf1SFEFN",
  "duration_ms": 269000
}
```

### 6.3 `POST /queue/bilibili`

请求体：

```json
{
  "video_id": "BV1QQSDBWEGn",
  "title": "【HiRes无损】周杰伦-太阳之子整张专辑 含歌词和单曲 共13首",
  "artist": "太阳之子周杰伦专辑",
  "album": "音乐综合",
  "duration_ms": 6555000,
  "cover_url": "https://i0.hdslb.com/...",
  "play_now": true
}
```

说明：

- `video_id` 支持 BV 号、av 号，或包含这两者的 B 站视频 URL
- 实际播放前会先将音频下载到服务端本地缓存，再交给 `voice-service`

### 6.4 `POST /queue`

这是最底层的通用入队接口，不会帮你解析平台歌曲信息。请求体：

```json
{
  "track_id": "custom:demo",
  "title": "Custom Song",
  "artist": "Someone",
  "source_url": "https://example.com/demo.mp3"
}
```

### 6.5 `POST /history/{history_id}/replay`

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `play_now` | boolean | 否 | 默认 `true` |

说明：

- 支持 `netease:*`、`qqmusic:*`、`bilibili:*` 三类历史记录
- 会重新解析新的播放 URL / 本地缓存，而不是重用旧 URL
- QQ 音乐历史重播仍依赖服务端已配置的管理员 QQ 音乐 cookie

## 7. 通用搜索与歌词接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/search` | 网易云搜索，返回原始结构包装在 `raw` 里 |
| `GET` | `/lyrics/{queue_item_id}` | 读取队列项歌词；B 站队列项会在可用时返回视频字幕时间轴，并在配置管理员 B 站登录态时尝试补抓 AI 字幕 |
| `GET` | `/playlist/detail` | 按请求头里的 `x-netease-cookie` 查询歌单详情 |

### 7.1 `GET /search`

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `keywords` | string | 是 | 关键词 |
| `limit` | integer | 否 | 默认 `20` |
| `offset` | integer | 否 | 默认 `0` |

响应：

```json
{
  "raw": {
    "result": {
      "songs": []
    }
  }
}
```

### 7.2 `GET /lyrics/{queue_item_id}`

说明：

- 队列项不存在时返回 `404`
- 网易云会优先尝试服务端管理员 cookie
- QQ 音乐会尝试使用服务端管理员 QQ 音乐 cookie
- B 站队列项会尝试读取视频字幕，并按歌曲标题/歌手倾向选择更合适的语言轨道
- 如果配置了管理员 B 站 Cookie，后端会在公开视频接口拿不到字幕时继续尝试登录态 API 和 Playwright 页面抓取

## 8. 网易云接口 `/netease/*`

### 8.1 用户态接口

这些接口需要 `x-netease-cookie`：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/netease/account` | 当前 cookie 对应账号信息 |
| `GET` | `/netease/likelist` | 喜欢歌曲 ID 列表，并尽量补充歌曲详情 |
| `GET` | `/netease/likes` | `/netease/likelist` 的别名 |
| `GET` | `/netease/playlists` | 当前用户歌单 |

`/netease/likelist` 支持：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `offset` | integer | 起始偏移 |
| `limit` | integer | 数量，`0` 表示尽量全部 |

### 8.2 登录二维码接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/netease/qr/key` | 申请二维码 key |
| `GET` | `/netease/qr/create` | 根据 key 生成二维码 |
| `GET` | `/netease/qr/check` | 轮询二维码状态 |

### 8.3 搜索与发现接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/netease/search/suggest` | 搜索建议 |
| `GET` | `/netease/search/hot` | 热搜 |
| `GET` | `/netease/search/default` | 默认搜索词 |
| `GET` | `/netease/playlist/categories` | 歌单分类 |
| `GET` | `/netease/playlist/hot` | 热门歌单分类 |
| `GET` | `/netease/playlist/top` | 网友精选歌单 |
| `GET` | `/netease/playlist/highquality` | 精品歌单 |
| `GET` | `/netease/playlist/{playlist_id}/detail` | 歌单详情 |
| `GET` | `/netease/song/{song_id}/lyric` | 歌词 |
| `GET` | `/netease/recommend/playlists` | 推荐歌单 |

`/netease/playlist/top` 支持参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `cat` | string | 分类，默认 `全部` |
| `limit` | integer | 默认 `50` |
| `offset` | integer | 默认 `0` |

`/netease/playlist/highquality` 支持参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `cat` | string | 分类，默认 `全部` |
| `limit` | integer | 默认 `20` |

### 8.4 服务端管理员 cookie 相关

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/netease/song/url` | 通过服务端已保存的管理员 cookie 获取歌曲播放 URL |

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 歌曲 ID |
| `level` | string | 否 | 默认 `auto`，支持 `auto`、`standard`、`higher`、`exhigh`、`lossless`、`hires`、`jyeffect`、`sky`、`dolby`、`jymaster` |

响应会额外返回：

- `requested_level`：本次请求的标准化音质
- `level`：上游实际返回的音质等级
- `br`：上游实际返回的码率

## 9. B 站接口 `/bilibili/*`

### 9.1 搜索接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/bilibili/search/videos` | 搜索 B 站视频，返回统一后的结果结构 |

关键参数：

| 路径 | 参数 | 说明 |
| --- | --- | --- |
| `/bilibili/search/videos` | `keywords` | 搜索词 |
| `/bilibili/search/videos` | `limit` | 默认 `20`，最大 `50` |
| `/bilibili/search/videos` | `page` | 默认 `1` |

返回项里的核心字段：

- `video_id`：BV 号或 av 号
- `title`：视频标题
- `artist`：UP 主名称
- `album`：视频分区或分类
- `description`：简介摘要
- `duration_ms`：时长，毫秒
- `artwork_url`：封面 URL
- `likes`：点赞数
- `favorites`：收藏数
- `coins`：投币数
- `webpage_url`：原始 B 站视频页

## 10. QQ 音乐接口 `/qqmusic/*`

### 10.1 搜索与内容接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/qqmusic/search` | 完整搜索接口 |
| `GET` | `/qqmusic/search/songs` | 简化歌曲搜索 |
| `GET` | `/qqmusic/song/{song_mid}/url` | 获取播放 URL |
| `GET` | `/qqmusic/song/{song_mid}/lyric` | 获取歌词 |
| `GET` | `/qqmusic/playlist/{playlist_id}` | 歌单详情 |
| `GET` | `/qqmusic/playlist/{playlist_id}/songs` | 歌单歌曲列表 |
| `GET` | `/qqmusic/playlist/{playlist_id}/name` | 歌单名称 |
| `GET` | `/qqmusic/album/{album_mid}` | 专辑详情 |
| `GET` | `/qqmusic/album/{album_mid}/name` | 专辑名称 |
| `GET` | `/qqmusic/singer/{singer_mid}` | 歌手信息 |
| `GET` | `/qqmusic/mv/{vid}` | MV 信息 |
| `GET` | `/qqmusic/album/{album_mid}/cover` | 专辑封面 URL |

关键参数：

| 路径 | 参数 | 说明 |
| --- | --- | --- |
| `/qqmusic/search` | `keywords` | 搜索词 |
| `/qqmusic/search` | `search_type` | 默认 `0`，歌曲 |
| `/qqmusic/search` | `limit` | 默认 `50` |
| `/qqmusic/search` | `page` | 默认 `1` |
| `/qqmusic/search/songs` | `keywords` | 搜索词 |
| `/qqmusic/song/{song_mid}/url` | `quality` | 默认 `320` |
| `/qqmusic/song/{song_mid}/lyric` | `parse` | `true` 时返回解析后的结构 |

### 10.2 登录与用户态接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/qqmusic/login/qr/key` | 获取 QQ 音乐登录二维码 |
| `GET` | `/qqmusic/login/qr/check` | 检查二维码状态 |
| `POST` | `/qqmusic/login/cookie` | 在当前进程内设置 QQ 音乐 cookie |
| `GET` | `/qqmusic/login/status` | 当前进程内登录状态 |
| `POST` | `/qqmusic/login/refresh` | 刷新登录状态 |
| `GET` | `/qqmusic/user/info` | 当前登录用户信息 |
| `GET` | `/qqmusic/user/playlists` | 当前登录用户歌单 |

`/qqmusic/login/qr/check` 查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `qr_key` | string | 是 | 二维码 key |
| `ptqrtoken` | string | 是 | 扫码 token |
| `pt_login_sig` | string | 否 | 登录签名 |

`/qqmusic/login/cookie` 请求体：

```json
{
  "cookie": "uin=...; qm_keyst=...; ..."
}
```

注意：

- `/qqmusic/login/cookie` 只把 cookie 写进当前进程内的 QQ 音乐客户端状态，不会持久化到数据库
- 如果你要长期保存管理员 QQ 音乐 cookie，应该使用 `/admin/qqmusic/*`

## 11. 管理接口 `/admin/*`

### 11.1 网易云管理员接口

| 方法 | 路径 | 是否需要 admin token | 说明 |
| --- | --- | --- | --- |
| `GET` | `/admin/status` | 否 | 是否已保存网易云管理员 cookie |
| `GET` | `/admin/account` | 是 | 当前管理员网易云账号信息 |
| `POST` | `/admin/cookie` | 是 | 写入网易云管理员 cookie |
| `GET` | `/admin/qr/key` | 是 | 获取管理员二维码 key |
| `GET` | `/admin/qr/create` | 是 | 生成管理员二维码 |
| `GET` | `/admin/qr/check` | 是 | 轮询并保存管理员 cookie |
| `POST` | `/admin/ts/description` | 是 | 设置 TeamSpeak 客户端简介 |
| `GET` | `/admin/debug/cookie` | 是 | cookie 指纹 |
| `GET` | `/admin/debug/config` | 是 | 配置指纹和关键配置 |
| `GET` | `/admin/debug/runtime` | 是 | 运行时路径信息 |
| `GET` | `/admin/debug/song_url` | 是 | 调试网易云歌曲 URL 解析 |

`POST /admin/cookie` 请求体：

```json
{
  "cookie": "MUSIC_U=...; __csrf=..."
}
```

`POST /admin/ts/description` 请求体：

```json
{
  "description": "TSBot online"
}
```

`GET /admin/debug/song_url` 查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 网易云歌曲 ID |

### 11.2 QQ 音乐管理员接口

| 方法 | 路径 | 是否需要 admin token | 说明 |
| --- | --- | --- | --- |
| `GET` | `/admin/qqmusic/status` | 是 | 是否已保存管理员 QQ 音乐 cookie |
| `POST` | `/admin/qqmusic/cookie` | 是 | 写入管理员 QQ 音乐 cookie |
| `POST` | `/admin/qqmusic/qr/confirm` | 是 | 将扫码授权后的 `auth_url` 换成最终 cookie 并保存 |

`POST /admin/qqmusic/cookie` 请求体：

```json
{
  "cookie": "uin=...; qm_keyst=..."
}
```

`POST /admin/qqmusic/qr/confirm` 请求体：

```json
{
  "auth_url": "https://graph.qq.com/..."
}
```

### 11.3 B 站管理员接口

| 方法 | 路径 | 是否需要 admin token | 说明 |
| --- | --- | --- | --- |
| `GET` | `/admin/bilibili/status` | 是 | 是否已保存管理员 B 站 cookie，以及 Playwright 是否可用 |
| `GET` | `/admin/bilibili/account` | 是 | 当前管理员 B 站账号信息 |
| `POST` | `/admin/bilibili/cookie` | 是 | 写入管理员 B 站 cookie |
| `POST` | `/admin/bilibili/qr/start` | 是 | 创建 B 站二维码登录会话并返回二维码图片 |
| `GET` | `/admin/bilibili/qr/check` | 是 | 轮询二维码登录状态，授权成功时保存管理员 cookie |

`POST /admin/bilibili/cookie` 请求体：

```json
{
  "cookie": "SESSDATA=...; bili_jct=..."
}
```

`GET /admin/bilibili/status` 响应示例：

```json
{
  "admin_cookie_set": true,
  "playwright_available": true,
  "playwright_dependency_installed": true
}
```

`POST /admin/bilibili/qr/start` 响应示例：

```json
{
  "session_id": "5f8f5c4e...",
  "qrcode_key": "bfb1d1caaffe7fac02522b3b32089d70",
  "qr_url": "https://account.bilibili.com/...",
  "qr_image_base64": "iVBORw0KGgoAAA..."
}
```

`GET /admin/bilibili/qr/check` 查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session_id` | string | 是 | `POST /admin/bilibili/qr/start` 返回的登录会话 ID |

## 12. 常见调用流程

### 12.1 外部机器人接入推荐流程

1. 配置 `TSBOT_API_TOKEN`
2. 调用 `/external/search`
3. 调用 `/external/queue`
4. 轮询 `/external/status`
5. 需要切歌时调用 `/external/player/action`

### 12.2 Web 控制台继续可用的配置

如果你开启了 `TSBOT_API_TOKEN`，又还要继续使用前端：

1. 后端设置 `TSBOT_API_TOKEN`
2. 前端构建前设置 `VITE_API_TOKEN`
3. 如果还要用管理员操作，再设置 `TSBOT_ADMIN_TOKEN`

### 12.3 需要更稳定的网易云和 QQ 音乐播放链接

建议额外配置：

- 网易云管理员 cookie：`/admin/cookie`
- QQ 音乐管理员 cookie：`/admin/qqmusic/cookie`

否则以下能力可能受限：

- 获取实际播放 URL
- 播放 VIP / 试听 / 登录态相关资源
- 拉取部分用户歌单或用户信息

## 13. 错误码与注意事项

常见 HTTP 状态：

| 状态码 | 含义 |
| --- | --- |
| `400` | 参数缺失或格式不正确 |
| `401` | 缺少或错误的 API token |
| `403` | 缺少或错误的 admin token，或歌曲不可播放 |
| `404` | 资源不存在 |
| `402` | 常用于“歌曲需要 VIP/付费” |
| `500` | 服务内部错误 |
| `502` | 上游音乐接口异常 |
| `503` | 上游暂时不可用 |

额外说明：

- 上游网易云和 QQ 音乐部分接口返回结构较复杂，某些 `/netease/*` 和 `/qqmusic/*` 路由会直接返回上游原始结构
- 如果你只是做外部控制集成，优先使用 `/external/*`
