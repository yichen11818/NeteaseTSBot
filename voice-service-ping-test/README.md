# voice-service-ping-test

后端驱动网易云音乐 / 本地音频在 TS 频道播放的测试与脚本集合。

所有操作都通过 HTTP / gRPC 完成——**不依赖 web 前端**。

---

## 0. 当前线上组件

| 进程 | 端口 | 用途 |
|---|---|---|
| `voice-service` (Rust, pid 3284425) | `127.0.0.1:9987` | gRPC 控制面（Play/Pause/Stop/GetStatus…），连 TS 频道发 opus 音频 |
| `backend` (uvicorn, pid 3283071) | `127.0.0.1:8009` | HTTP API，对接 NeteaseCloudMusicApi，处理 cookie/队列/历史 |

外部依赖：

- 网易云 API：`http://47.113.188.213:3000/`（`NeteaseCloudMusicApi` 公共镜像）
- TS6 服务器：`127.0.0.1:9987` 语音 / `127.0.0.1:10022` ServerQuery SSH
- 你的网易云 cookie：加密存于 `tsbot.db` 的 `secrets` 表，密钥 `tsbot.env` 的 `TSBOT_COOKIE_KEY`

---

## 1. 直接使用脚本（推荐）

`play.sh`——按关键词搜网易云、自动取第一首、加队列/立刻播放：

```bash
# 默认播 周深 - 大鱼
./play.sh

# 按关键词搜 + 立刻播
./play.sh "陈奕迅 十年"
./play.sh "周杰伦 晴天"
./play.sh "Beyond 海阔天空"

# 指定音质（默认 auto，可选 standard/higher/exhigh/lossless/hires/...）
./play.sh -l higher "陈奕迅 十年"

# 只入队不立刻播（之后用 /voice/play 触发，或下一首自动接上）
./play.sh -n "陈奕迅 十年"

# 入队 + 立刻播 + 4 秒后停（用于自动化测试）
./play.sh -s "陈奕迅 十年"
```

`play.sh` 内部完整调用链：
1. `GET  /search?keywords=…&limit=1` → 取第一首 `song_id/title/artist/duration`
2. `POST /queue/netease` 带 `song_id + title + artist + duration_ms + level + play_now`
3. backend → NeteaseCloudMusicApi `/song/url/v1` → 拿到 mp3 URL → 调 `voice.play(source_url=url, ...)` → voice-service 通过 ffmpeg 拉流 → opus 编码 → TS 频道

环境变量覆盖：
- `TSBOT_BACKEND=http://x.y.z.w:8009` 自定义 backend 地址

---

## 2. 直接用 curl（不依赖脚本）

### 2.1 搜索

```bash
curl -s -G --data-urlencode "keywords=陈奕迅 十年" --data "limit=5" \
    http://127.0.0.1:8009/search | jq '.result.songs[] | {id,name,artists:[.artists[].name],fee,duration}'
```

### 2.2 加队列（不立刻播）

```bash
curl -s -X POST -H "Content-Type: application/json" \
    -d '{"song_id":"66842","title":"十年","artist":"陈奕迅","play_now":false}' \
    http://127.0.0.1:8009/queue/netease
# -> {"ok":true,"id":N,"trial":false}
```

### 2.3 立刻播放

```bash
curl -s -X POST -H "Content-Type: application/json" \
    -d '{"song_id":"66842","title":"十年","artist":"陈奕迅","play_now":true,"level":"standard"}' \
    http://127.0.0.1:8009/queue/netease
# -> {"ok":true,"id":N,"trial":false}     # trial:false = 完整版；true = 30s 试听
```

`level` 取值见 `backend/main.py:883`：`auto / standard / higher / exhigh / lossless / hires / jymaster / sky / dolby / jyeffect`，实际能不能拿到对应码率取决于你网易云账号的权益。

### 2.4 控制播放

```bash
# 当前状态
curl http://127.0.0.1:8009/voice/status | jq

# 暂停
curl -X POST http://127.0.0.1:8009/voice/pause

# 恢复（用 /voice/play，pause 状态下它会触发 resume）
curl -X POST http://127.0.0.1:8009/voice/play

# 停止当前播放：backend HTTP 没有 /voice/stop 端点。
# Play_now=true 后想停，请用 voice-service gRPC 的 Stop(Empty())，或者：
#   1) curl -X POST http://127.0.0.1:8009/voice/play   # 会自动播队列里下一个 item
#   2) 或重启 voice-service 让它重新连 TS

# 跳到下一首/上一首（自动播队列下一项）
curl -X POST http://127.0.0.1:8009/voice/next
curl -X POST http://127.0.0.1:8009/voice/previous

# 音量
curl -X PUT -H "Content-Type: application/json" -d '{"volume_percent":80}' \
    http://127.0.0.1:8009/voice/volume

# 跳到指定秒
curl -X POST -H "Content-Type: application/json" -d '{"time":60.0}' \
    http://127.0.0.1:8009/voice/seek

# 队列 / 历史
curl http://127.0.0.1:8009/queue
curl http://127.0.0.1:8009/history
```

---

## 3. 直接调 voice-service gRPC（最低层）

不想走 backend 时，可以直接用 `voice_service_pb` 桩（已 vendored 在本目录下）：

```python
# play_pause_test.py / play_netease.py 都是这种风格
import grpc, voice_pb2 as pb, voice_pb2_grpc as pb_grpc
ch = grpc.insecure_channel("127.0.0.1:9987")
stub = pb_grpc.VoiceServiceStub(ch)

# 健康检查
stub.Ping(pb.Empty())            # {"version": "0.1.0"}

# 播一个本地文件或公网 URL（任何 ffmpeg 能解的 source）
stub.Play(pb.PlayRequest(
    source_url="file:///tmp/foo.mp3",   # 或 "http://...", "https://..."
    title="我的歌",
    notice="",
))

# 状态
print(stub.GetStatus(pb.Empty()))   # state: 1=IDLE 2=PLAYING 3=PAUSED
```

只播本地音频 / 任意 URL（不需要网易云）时这条最快。

---

## 4. 验证测试脚本

| 脚本 | 用途 |
|---|---|
| `ping_test.py` | 测 gRPC Ping/GetStatus/GetAudioFx/SubscribeEvents |
| `play_pause_test.py` | 测 Play/Pause/Stop/Replace-playback 状态机 |
| `play_netease.py` | 不依赖 backend，直接调 NeteaseCloudMusicApi + gRPC Play |

跑法：

```bash
../backend/.venv/bin/python ping_test.py
../backend/.venv/bin/python play_pause_test.py
../backend/.venv/bin/python play_netease.py "Beyond 海阔天空"
```

需要：

- 一个 2 秒 440Hz sine wav 在 `/tmp/voice-test-audio/ping-sine.wav`（`play_pause_test.py` 第一次跑会自动生成）
- voice-service gRPC 在 `127.0.0.1:9987`
- NeteaseCloudMusicApi 可达（默认 `http://47.113.188.213:3000/`）

---

## 5. 配置入口

### 5.1 启动 backend

```bash
cd /root/tsbot
source tsbot.env
export TSBOT_VOICE_GRPC_ADDR=127.0.0.1:9987          # 必须：当前 voice-service 实际监听 9987，不是 50051
export TSBOT_NETEASE_API_BASE=http://47.113.188.213:3000/   # 覆盖 tsbot.env 默认的 127.0.0.1:3000
exec /root/tsbot/backend/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8009 \
    > /root/tsbot/logs/backend.log 2>&1
```

如果要让 backend 在外网可访问，加 `--host 0.0.0.0`。

### 5.2 启动 voice-service

```bash
cd /root/tsbot/voice-service
exec ./target/debug/voice-service 127.0.0.1:9987 > /root/tsbot/logs/voice.log 2>&1
```

stdout 一定**重定向到文件**——内部用 `tracing_subscriber::fmt().with_writer(io::stdout)`，否则日志全丢。

### 5.3 设置 / 更换 cookie

```python
import json, urllib.request
COOKIE = "MUSIC_U=xxxx; MUSIC_R_U=yyyy"   # 从浏览器复制
req = urllib.request.Request(
    "http://127.0.0.1:8009/admin/cookie",
    data=json.dumps({"cookie": COOKIE}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
print(urllib.request.urlopen(req, timeout=10).read())
```

验证：
```bash
curl http://127.0.0.1:8009/admin/account
# {"user_id":..., "nickname":..., "vip_type":0}
```

cookie 字符串本身**不要写进任何文件 / git / shell history**——它在 backend 内部用 `TSBOT_COOKIE_KEY` 加密落 `secrets` 表。设了 `TSBOT_ADMIN_TOKEN` 时还要在请求头带 `x-admin-token: ...`。

---

## 6. 已知坑 & 注意

1. **voice-service 重连 bug**：`vendor/tsclientlib-0.2.0/src/lib.rs` 的 `ConnectionState::Finished` 修复保留了下来，但**首次 connect 失败后 ts3_actor 不会再重试**（除非等到下一次成功 connect 之后才掉线才会走 backoff）。解决办法：手动 `kill <pid>` 然后重启，第一次会撞 `ClientTooManyClonesConnected`，30 秒后自动重试成功。
2. **cookie 路径 vs trial**：cookie 不对时 backend 的 `_get_admin_cookie` 在 `play_now=true` 路径直接 400，不会走 trial 降级。要么给正确 cookie，要么用 `play_netease.py` 直接绕过 backend（自己调 NeteaseCloudMusicApi）。
3. **level 与 VIP**：账号非 VIP 时高码率（exhigh/lossless）会拿不到，返回 `trial:true` 或 `fee:1`。网易云侧策略，不在 backend 范围内。
4. **client_description 同步**：backend 默认不更新 bot 在 TS 上的"正在播放"描述。要打开加 `TSBOT_TS3_ALLOW_DIRECT_CLIENTUPDATE_DESCRIPTION=1`，或配 ServerQuery。
5. **TS 连接一旦掉，播放立刻静默**：opus 包会卡在 `ts3_audio_tx` 队列里没人接收；`/voice/status` 仍显示 playing，但频道里听不到。看到 `audio_send_diag` 不再增长、`out_buf_max=0 send_audio_errs=0` 但 state=playing，就是这种情况。需要重连 voice-service。
6. **tsbot.env 里 `TSBOT_VOICE_GRPC_ADDR=127.0.0.1:50051`** 和 `TSBOT_NETEASE_API_BASE=http://127.0.0.1:3000/` 都是过时的。启动 backend 时务必显式 export 覆盖，否则连不上。

---

## 7. 文件位置

```
/root/tsbot/voice-service-ping-test/
├── ping_test.py            # gRPC 健康/状态/事件流烟雾测试
├── play_pause_test.py      # gRPC Play/Pause/Stop 状态机测试
├── play_netease.py         # 绕 backend 直接 NeteaseCloudMusicApi → gRPC Play
├── play.sh                 # 按关键词搜 + 立刻播的封装脚本
├── voice_service_pb/       # vendored gRPC 桩（voice_pb2.py + voice_pb2_grpc.py）
├── proto/voice.proto       # 服务契约
└── README.md               # 本文件
```