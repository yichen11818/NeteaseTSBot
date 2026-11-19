# 各来源请求音质 / Provider quality defaults

管理员在「配置 → 网易云音乐 / QQ 音乐」分别设置默认请求音质，保存后点击「应用配置」。数据库持久化，后端重启后仍保留；首次初始化可通过 `TSBOT_NETEASE_DEFAULT_QUALITY=auto`、`TSBOT_QQMUSIC_DEFAULT_QUALITY=320` 设置。应用不重启语音服务、不打断播放、不修改已有队列条目的音质。

| 来源 | 当前适配器支持的请求值 | 兼容默认 |
| --- | --- | --- |
| 网易云 | auto, standard, higher, exhigh, lossless, hires, jyeffect, sky, dolby, jymaster | auto |
| QQ 音乐 | m4a（C400）、128（M500）、320（M800） | 320 |

这些是请求档位。QQ 当前没有实现 FLAC/Hi-Res，不将 M4A 标为未经确认的固定码率；平台资源、会员权限、风控和试听仍会影响实际返回。网易云 `auto` 仍表示自动最高（请求 jymaster），保留已有风控时回退标准音质一次的逻辑。明确指定的档位沿用原有行为。

优先级：明确指定请求音质 > 对应来源的服务器默认值。省略字段或传 null 表示跟随服务器，空字符串和未知档位不代表跟随。网易云使用 `level`，QQ 使用 `quality`；不接受其他来源的档位或错误的平台字段。

播放器右下角「音效与音质偏好」分别提供浏览器覆盖，默认「跟随服务器」，并显示服务器当前默认值。两个平台使用独立的浏览器存储键。已有有效网易云偏好会保留，包括 `auto`；新浏览器不再强制发送 `auto` 或 QQ `320`。跟随时不发送音质字段。

Web 点播与批量网易云歌单、现有网易云聊天命令、历史重播和外部入队 API 都通过后端入队边界选择音质。历史重播创建新的队列条目，省略档位时采用当前服务器默认值。已有队列条目在重复播放、重试和刷新过期地址时保留其最初选择；兼容旧网易云元数据及通过 QQ C400/M500/M800 文件名识别的旧记录。此功能不添加 QQ 聊天或 QQ 歌单导入。

`GET /config/public` 返回 `music_quality.netease`、`music_quality.qqmusic`，各含安全的 `default` 和 `options`。历史重播的明确覆盖通过查询参数传递，例如 `/external/history/1/replay?play_now=false&quality=128`。

Server defaults are provider-specific, persisted in runtime settings, and only affect new enqueue requests. Omitted/null means follow server; explicit Netease auto still means automatic highest. The browser preserves existing valid Netease preferences and offers independent follow-server choices for both providers. Queue refresh/repeat/retry retains the original selection; history replay is a new enqueue. Requested quality does not guarantee entitlement, full-track playback or an actual format. No QQ chat/playlist support is added.
