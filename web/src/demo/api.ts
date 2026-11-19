// All demo changes live in this tab's memory. This module never makes network requests.
const cover = `${import.meta.env.BASE_URL}demo-cover.svg`
const catalogue = [
  { id: 101, name: '一起听见 · Together', artist: 'TSBot Sessions', album: 'Channel One', duration: 186 },
  { id: 102, name: '深夜频道 · Night Channel', artist: 'Demo Ensemble', album: 'Channel One', duration: 214 },
  { id: 103, name: '周末电台 · Weekend Radio', artist: 'TSBot Sessions', album: 'Open Frequency', duration: 172 },
  { id: 104, name: '等你上线 · Back Online', artist: 'Demo Ensemble', album: 'Open Frequency', duration: 203 },
]
type Song = typeof catalogue[number]
type Track = { id: number; title: string; artist: string; album: string; artwork: string; duration: number; track_id: string }
function track(song: Song, id: number, source = 'netease'): Track {
  return { id, title: song.name, artist: song.artist, album: song.album, artwork: cover, duration: song.duration, track_id: `${source}:${song.id}` }
}
function neteaseSong(song: Song) {
  return { id: song.id, name: song.name, ar: [{ name: song.artist }], al: { name: song.album, picUrl: cover }, dt: song.duration * 1000 }
}
const initialQueue = () => catalogue.slice(0, 3).map((song, i) => track(song, i + 1))
let queue = initialQueue()
let nextId = 4
let currentId: number | null = 1
let playing = false
let position = 24
let updatedAt = Date.now()
let volume = 65
let shuffled = false
let repeat = 'all'
let history = [track(catalogue[3], 1)]
let fx = { pan: 0, width: 1, swap_lr: false, bass_db: 0, reverb_mix: 0 }
const initialSettings = () => ({
  'web.app_name': 'TSBot 在线体验',
  'backend.voice_grpc_addr': 'voice-service:50051',
  'backend.netease_api_base': 'http://netease-api:3000/',
  'backend.netease_default_quality': 'auto',
  'backend.qqmusic_default_quality': '320',
  'voice.ts3_host': 'ts.example.com',
  'voice.ts3_port': 9987,
  'voice.ts3_nickname': 'TSBot Demo',
  'voice.ts3_channel_id': '',
  'voice.ts3_channel_path': '一起听歌',
})
let settings: Record<string, string | number> = initialSettings()
let applyPending = false
const labels: Record<string, string> = {
  'web.app_name': '界面名称', 'backend.voice_grpc_addr': 'Voice gRPC 地址',
  'backend.netease_api_base': '网易云 API 地址', 'voice.ts3_host': 'TeamSpeak 服务器',
  'voice.ts3_port': 'TeamSpeak 端口', 'voice.ts3_nickname': '机器人昵称',
  'voice.ts3_channel_id': '频道 ID', 'voice.ts3_channel_path': '频道路径',
  'backend.netease_default_quality': '默认请求音质', 'backend.qqmusic_default_quality': '默认请求音质',
}

const qualityOptions: Record<string, string[]> = {
  'backend.netease_default_quality': ['auto', 'standard', 'higher', 'exhigh', 'lossless', 'hires', 'jyeffect', 'sky', 'dolby', 'jymaster'],
  'backend.qqmusic_default_quality': ['m4a', '128', '320'],
}

export function resetDemo() {
  queue = initialQueue(); nextId = 4; currentId = 1; playing = false; position = 24
  updatedAt = Date.now(); volume = 65; shuffled = false; repeat = 'all'
  history = [track(catalogue[3], 1)]
  fx = { pan: 0, width: 1, swap_lr: false, bass_db: 0, reverb_mix: 0 }
  settings = initialSettings(); applyPending = false
}
function choose(id: number | null) {
  currentId = id; position = 0; updatedAt = Date.now(); playing = id !== null
  const selected = queue.find(item => item.id === id)
  if (selected) history = [{ ...selected, id: Date.now() }, ...history].slice(0, 30)
}
function updateClock() {
  if (playing) position += (Date.now() - updatedAt) / 1000
  updatedAt = Date.now()
  const selected = queue.find(item => item.id === currentId)
  if (selected && position >= selected.duration) {
    if (repeat === 'one') position %= selected.duration
    else advance(1)
  }
}
function advance(direction: number) {
  const index = queue.findIndex(item => item.id === currentId)
  let next = index + direction
  if (shuffled && queue.length > 1) next = (index + 1 + Math.floor(Math.random() * (queue.length - 1))) % queue.length
  if (repeat === 'all' && queue.length) next = (next + queue.length) % queue.length
  choose(queue[next]?.id ?? null)
}
function payload() {
  return { fields: Object.entries(settings).map(([key, value]) => ({
    key, value, label: labels[key], group: key.includes('netease_') ? 'music_netease' : key.includes('qqmusic_') ? 'music_qqmusic' : key.startsWith('voice.') ? 'teamspeak' : key.startsWith('web.') ? 'web' : 'backend',
    type: qualityOptions[key] ? 'select' : typeof value === 'number' ? 'integer' : key.endsWith('_base') ? 'url' : 'string',
    sensitive: false, configured: true, restart: key.startsWith('voice.') ? 'voice' : 'none',
    minimum: key.endsWith('_port') ? 1 : null, maximum: key.endsWith('_port') ? 65535 : null, options: qualityOptions[key] ?? [], help: qualityOptions[key] ? '请求音质不保证实际格式或完整歌曲；平台权限与试听限制仍适用。' : '',
  })), assets: [], bootstrap: { demo: true }, apply_pending: applyPending }
}
function check(id: string, label: string, detail: string) {
  return { id, label, status: 'success', detail, action: '', group: 'backend', required: true }
}

export function demoRequest(path: string, init: RequestInit = {}): unknown {
  const url = new URL(path, 'https://demo.invalid')
  const route = url.pathname
  const method = init.method || 'GET'
  const body = typeof init.body === 'string' ? JSON.parse(init.body) : {}
  const auth = { initialized: true, authenticated: true, must_change_password: false, username: 'demo', csrf_token: '' }
  updateClock()
  let result: unknown
  if (method === 'GET' && route === '/auth/status') result = auth
  else if (method === 'GET' && route === '/config/public') result = { app_name: settings['web.app_name'], app_icon: '', log_level: 'WARN', music_quality: {
    netease: { default: settings['backend.netease_default_quality'], options: qualityOptions['backend.netease_default_quality'] },
    qqmusic: { default: settings['backend.qqmusic_default_quality'], options: qualityOptions['backend.qqmusic_default_quality'] },
  } }
  else if (method === 'GET' && route === '/voice/status') {
    const selected = queue.find(item => item.id === currentId)
    result = { state: selected ? playing ? 'playing' : 'paused' : 'idle', track_id: selected?.id,
      now_playing_title: selected?.title || '', now_playing_artist: selected?.artist || '', now_playing_album: selected?.album || '',
      artwork_url: selected?.artwork || '', current_time: position, duration: selected?.duration || 0,
      volume_percent: volume, is_shuffled: shuffled, repeat_mode: repeat,
      voice_connected: true, teamspeak_connected: true, voice_config_revision: 'demo' }
  } else if (route === '/queue' && method === 'GET') result = queue
  else if (route === '/queue' && method === 'DELETE') { queue = []; choose(null); result = { ok: true } }
  else if (route === '/queue/reorder' && method === 'POST') {
    const ids = body.track_ids as number[]
    if (!Array.isArray(ids) || ids.length !== queue.length || new Set(ids).size !== queue.length || ids.some(id => !queue.some(item => item.id === id))) throw new Error('队列顺序无效')
    queue = ids.map(id => queue.find(item => item.id === id)!); result = { ok: true }
  } else if (/^\/queue\/\d+\/play$/.test(route) && method === 'POST') {
    const id = Number(route.split('/')[2])
    if (!queue.some(item => item.id === id)) throw new Error('队列项目不存在')
    choose(id); result = { ok: true }
  } else if (/^\/queue\/\d+$/.test(route) && method === 'DELETE') {
    const id = Number(route.split('/')[2]); queue = queue.filter(item => item.id !== id)
    if (currentId === id) choose(queue[0]?.id ?? null)
    result = { ok: true }
  } else if (/^\/queue\/(netease|qqmusic|bilibili)$/.test(route) && method === 'POST') {
    const source = route.split('/')[2]
    const song = catalogue.find(item => String(item.id) === String(body.track_id || body.song_id || body.song_mid || '').replace('demo', '') || `BVdemo${item.id}` === body.video_id) || catalogue[0]
    const item = track(song, nextId++, source); queue.push(item)
    if (body.play_now) choose(item.id)
    result = { ok: true, id: item.id, source_url: '' }
  } else if (route.startsWith('/voice/') && method !== 'GET') {
    if (route === '/voice/play') { if (currentId === null) choose(queue[0]?.id ?? null); else playing = true }
    else if (route === '/voice/pause') playing = false
    else if (route === '/voice/stop') choose(null)
    else if (route === '/voice/next') advance(1)
    else if (route === '/voice/previous') advance(-1)
    else if (route === '/voice/seek') position = Math.min(Math.max(0, Number(body.time) || 0), queue.find(item => item.id === currentId)?.duration || 0)
    else if (route === '/voice/volume') volume = Math.min(100, Math.max(0, Number(body.volume_percent) || 0))
    else if (route === '/voice/shuffle') shuffled = !!body.enabled
    else if (route === '/voice/repeat') repeat = ['none', 'one', 'all'].includes(body.mode) ? body.mode : 'none'
    else if (route === '/voice/fx') fx = { ...fx, ...body }
    else throw new Error('演示模式不支持此操作')
    result = { ok: true }
  } else if (route === '/voice/fx' && method === 'GET') result = fx
  else if (route === '/search' && method === 'GET') {
    const keyword = (url.searchParams.get('keywords') || '').toLowerCase()
    const songs = catalogue.filter(song => `${song.name} ${song.artist} ${song.album}`.toLowerCase().includes(keyword))
    result = { raw: { result: { songs: songs.map(neteaseSong), songCount: songs.length } } }
  } else if (route === '/qqmusic/search/songs' && method === 'GET') {
    const keyword = (url.searchParams.get('keywords') || '').toLowerCase()
    result = { songs: catalogue.filter(song => `${song.name} ${song.artist}`.toLowerCase().includes(keyword)).map(song => ({ ...neteaseSong(song), mid: `demo${song.id}`, singer: [{ name: song.artist }], album: { name: song.album }, interval: song.duration })) }
  } else if (route === '/bilibili/search/videos' && method === 'GET') {
    const keyword = (url.searchParams.get('keywords') || '').toLowerCase()
    result = { items: catalogue.filter(song => `${song.name} ${song.artist}`.toLowerCase().includes(keyword)).map(song => ({ video_id: `BVdemo${song.id}`, title: song.name, artist: song.artist, album: song.album, artwork_url: cover, duration_ms: song.duration * 1000, description: '交互演示数据，不对应真实平台视频。' })), has_more: false }
  } else if (route === '/netease/search/hot') result = { result: { hots: catalogue.map(song => ({ first: song.name })) } }
  else if (route === '/netease/search/default') result = { data: { showKeyword: '一起听见' } }
  else if (route === '/netease/search/suggest') result = { result: { allMatch: catalogue.map(song => ({ keyword: song.name })) } }
  else if (route === '/netease/playlist/categories') result = { sub: [{ name: '全部' }, { name: '轻音乐' }] }
  else if (/^\/netease\/playlist\/\d+\/detail$/.test(route)) {
    result = { playlist: { id: Number(route.split('/')[3]), name: '一起听歌 · TSBot Sessions', coverImgUrl: cover, creator: { nickname: 'TSBot' }, description: '示例歌单，可尝试添加到队列。演示不会播放真实音频。', tracks: catalogue.map(neteaseSong), trackCount: catalogue.length, playCount: 1280, tags: ['轻音乐'] } }
  } else if (['/netease/playlist/top', '/netease/playlist/highquality', '/netease/recommend/playlists'].includes(route)) {
    const playlists = [1, 2, 3].map(id => ({ id, name: ['一起听歌', '深夜频道', '周末电台'][id - 1], coverImgUrl: cover, picUrl: cover, trackCount: 4, playCount: 1280, creator: { nickname: 'TSBot' } }))
    result = { playlists, result: playlists }
  } else if (route === '/netease/likes') result = { songs: catalogue.map(neteaseSong), has_more: false, offset: 0, limit: 200 }
  else if (route.startsWith('/lyrics/')) result = { lyrics: [
    { time: 0, text: '欢迎来到 TSBot 在线体验' }, { time: 8000, text: '把喜欢的旋律加入队列' },
    { time: 16000, text: '和频道里的朋友一起听见' }, { time: 26000, text: '这里展示歌词同步，不播放真实音频' },
    { time: 40000, text: '部署后连接你的 TeamSpeak 频道' },
  ] }
  else if (route === '/history' && method === 'GET') result = history.map(item => ({ ...item, played_at: new Date(Date.now() - 3600000).toISOString() }))
  else if (/^\/history\/\d+\/replay$/.test(route) && method === 'POST') {
    const source = history.find(item => item.id === Number(route.split('/')[2]))
    if (!source) throw new Error('历史记录不存在')
    const item = { ...source, id: nextId++ }; queue.push(item)
    if (url.searchParams.get('play_now') === 'true') choose(item.id)
    result = { ok: true, id: item.id }
  } else if (route === '/admin/settings' && method === 'GET') result = payload()
  else if (route === '/admin/settings' && method === 'PUT') {
    const values = body.values || {}
    if (Object.keys(values).some(key => !Object.prototype.hasOwnProperty.call(settings, key))) throw new Error('演示模式不接收密码或平台凭据')
    settings = { ...settings, ...values }; applyPending = !body.apply
    result = { ...payload(), ok: true, voice_restart_requested: false }
  } else if (route === '/admin/diagnostics' && method === 'GET') result = { demo: true, ready: true, checks: [
    check('backend', '后端服务', '模拟后端就绪'), check('voice', 'Voice 服务', '模拟语音服务就绪'),
    check('teamspeak', 'TeamSpeak 连接', '模拟机器人已连接；未连接真实服务器'), check('netease', '网易云 API', '模拟音乐接口就绪'),
  ] }
  else if (['/admin/status', '/admin/qqmusic/status', '/admin/bilibili/status', '/qqmusic/login/status'].includes(route) && method === 'GET') result = { admin_cookie_set: true, logged_in: true, playwright_available: true, demo: true }
  else throw new Error('演示模式不连接真实账号或服务。请部署后使用此功能。')
  // Match JSON transport semantics; callers must not mutate the shared demo state.
  return JSON.parse(JSON.stringify(result))
}
