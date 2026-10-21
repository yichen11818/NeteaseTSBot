<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Check, Eye, EyeOff, Image as ImageIcon, KeyRound, LogOut, RefreshCw, Save, ServerCog, Trash2, Upload } from 'lucide-vue-next'
import { apiDelete, apiGet, apiPut, apiPutFile, apiUrl } from '../api'
import { logout } from '../auth'
import { loadAppBranding } from '../appConfig'
import FloatingToast from '../components/FloatingToast.vue'
import CookieView from './CookieView.vue'
import { DEMO_MODE } from '../demoMode'

interface SettingField {
  key: string
  group: string
  label: string
  type: 'string' | 'integer' | 'boolean' | 'secret' | 'password' | 'url' | 'select' | 'multiline'
  value: unknown
  configured: boolean
  sensitive: boolean
  restart: 'none' | 'voice' | 'backend'
  minimum: number | null
  maximum: number | null
  options: string[]
  help: string
}

interface SettingsPayload {
  fields: SettingField[]
  assets: ManagedAsset[]
  bootstrap: Record<string, unknown>
  voice_restart_requested?: boolean
  voice_config_revision?: string
  backend_restart_required?: boolean
  apply_pending?: boolean
}

interface ManagedAsset {
  key: string
  group: string
  label: string
  configured: boolean
  url: string
  version: number
  restart: 'none' | 'voice'
  accept: string
  max_size_mb: number
  storage_path: string
  help: string
}

const GROUPS = [
  { id: 'teamspeak', label: 'TeamSpeak 连接', section: 'common', summary: '服务器、频道与机器人资料', description: '设置机器人要加入的语音服务器和频道，以及机器人在 TeamSpeak 中显示的昵称、头像与简介。' },
  { id: 'authorization', label: '音乐账号登录', section: 'common', summary: '网易云、QQ 音乐与 B 站账号', description: '连接你的音乐平台账号，用于读取个人歌单、收藏及账号有权限使用的音乐内容。各平台分别登录。' },
  { id: 'music', label: '音乐接口与缓存', section: 'common', summary: '音乐服务地址与下载限制', description: '配置网易云音乐 API 地址，以及 B 站点播时长和音频缓存大小。QQ 音乐与 B 站使用内建接口，无需填写服务地址。' },
  { id: 'web', label: '界面外观', section: 'common', summary: '网页名称与图标', description: '修改网页显示名称和浏览器标签页图标，用于定制自己的机器人界面。' },
  { id: 'backend', label: '服务与日志', section: 'advanced', summary: '语音服务通信与问题排查', description: '配置后端与 Voice 语音服务的通信地址、各服务日志等级和播放状态文件。连接异常或排查问题时使用。' },
  { id: 'access', label: '外部 API', section: 'advanced', summary: '供脚本与其他系统调用', description: '为外部程序调用机器人接口配置访问 Token，适合接入脚本或其他系统。多个 Token 使用逗号分隔。' },
  { id: 'serverquery', label: 'ServerQuery 兼容', section: 'advanced', summary: 'TeamSpeak 管理接口', description: '配置 TeamSpeak 的 ServerQuery 管理接口，供机器人更新头像、简介等资料时使用。通常只在需要此兼容方式时配置。' },
] as const

const NAV_SECTIONS = [
  { id: 'common', label: '常用设置', groups: GROUPS.filter(group => group.section === 'common') },
  { id: 'advanced', label: '高级设置', groups: GROUPS.filter(group => group.section === 'advanced') },
]

const FIELD_HELP: Record<string, string> = {
  'voice.ts3_host': '填写 TeamSpeak 服务器域名或 IP，不要包含 http:// 或 https://。',
  'voice.ts3_port': 'TeamSpeak 语音连接使用的 UDP 端口，通常为 9987。',
  'voice.ts3_nickname': '机器人加入频道后显示的名称。',
  'voice.ts3_server_password': '服务器设置了加入密码时填写；已有密码留空不修改。',
  'voice.ts3_channel_id': '机器人要加入的频道 ID。与频道路径二选一；均留空时使用默认频道。',
  'voice.ts3_channel_path': '用频道名称路径指定目标频道；已填写频道 ID 时通常无需再填。',
  'voice.ts3_channel_password': '目标频道设有加入密码时填写。',
  'voice.ts3_identity_file': 'Voice 服务读取的身份文件路径。保留原文件可让机器人延续已有身份与权限。',
  'voice.ts3_identity': '直接指定 TeamSpeak 身份内容；通常保留现有身份文件即可，无需填写。',
  'voice.allow_direct_description': '允许通过 TeamSpeak 客户端连接直接更新机器人简介。',
  'voice.description_title': '显示在机器人 TeamSpeak 客户端简介中的标题。',
  'voice.description_intro': '显示在机器人 TeamSpeak 客户端简介中的说明文字。',
  'backend.netease_api_base': '填写单独部署的 NeteaseCloudMusicApi 服务地址，用于网易云搜索、歌单及播放。',
  'backend.bilibili_max_duration_minutes': '限制单个 B 站点播视频的长度，避免下载过长内容。',
  'backend.bilibili_audio_cache_ttl_hours': '缓存音频保留多久，过期内容会被清理。',
  'backend.bilibili_audio_cache_max_mb': '限制 B 站音频缓存占用的磁盘空间。',
  'backend.bilibili_audio_partial_ttl_minutes': '未完成的下载保留多久，避免临时文件长期占用空间。',
  'backend.voice_grpc_addr': '后端连接 Voice 的地址。源码部署通常为 127.0.0.1:50051，Docker 部署通常为 voice-service:50051。',
  'backend.log_level': '控制后端日志详细程度。排查问题时可临时使用 DEBUG。',
  'backend.log_file': '后端日志写入的位置，用于查看请求和运行错误。',
  'web.log_level': '控制浏览器控制台中前端日志的详细程度。',
  'voice.log_level': '控制 Voice 语音服务日志的详细程度。',
  'voice.state_file': '保存播放状态的文件路径，供 Voice 恢复运行状态使用。',
  'voice.serverquery_user': 'TeamSpeak ServerQuery 管理账号，与音乐账号无关。',
  'voice.serverquery_password': '上述 ServerQuery 管理账号的密码。',
  'voice.serverquery_host': 'ServerQuery 管理接口所在服务器的域名或 IP。',
  'voice.serverquery_port': 'ServerQuery 管理端口，通常为 TCP 10011，不是语音端口 9987。',
  'voice.serverquery_sid': '需要管理的 TeamSpeak 虚拟服务器 ID。',
  'voice.serverquery_use_port': '通过语音端口定位需要管理的 TeamSpeak 虚拟服务器。',
}

const GROUP_ALIASES: Record<string, string> = {
  setup: 'teamspeak',
  description: 'teamspeak',
  voice: 'backend',
}

const router = useRouter()
const route = useRoute()
const payload = ref<SettingsPayload | null>(null)
const rawRequestedGroup = String(route.query.group || '')
const requestedGroup = GROUP_ALIASES[rawRequestedGroup] || rawRequestedGroup
const activeGroup = ref(GROUPS.some((group) => group.id === requestedGroup) ? requestedGroup : 'teamspeak')
const draft = ref<Record<string, any>>({})
const revealed = ref<Record<string, boolean>>({})
const assetBusy = ref<Record<string, boolean>>({})
const loading = ref(true)
const saving = ref(false)
const applying = ref(false)
const error = ref('')
const toastMessage = ref('')
const toastType = ref<'success' | 'error' | 'info'>('info')
let toastTimer: ReturnType<typeof setTimeout> | null = null
let waitGeneration = 0

const activeCategory = computed(() => GROUPS.find(group => group.id === activeGroup.value)!)
const activeFields = computed(() => payload.value?.fields.filter((field) => (field.key === 'web.log_level' ? 'backend' : field.group) === activeGroup.value) || [])
const activeAssets = computed(() => payload.value?.assets.filter((asset) => asset.group === activeGroup.value) || [])
const activeNeedsVoiceRestart = computed(() => (
  activeFields.value.some((field) => field.restart === 'voice')
  || activeAssets.value.some((asset) => asset.restart === 'voice')
))

function hydrate(result: SettingsPayload) {
  payload.value = result
  const next: Record<string, any> = {}
  for (const field of result.fields) {
    next[field.key] = field.sensitive ? '' : field.value
  }
  draft.value = next
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    hydrate(await apiGet<SettingsPayload>('/admin/settings'))
  } catch (e: any) {
    error.value = String(e?.message || e)
    showToast(error.value, 'error', 8000)
  } finally {
    loading.value = false
  }
}

function showToast(message: string, type: 'success' | 'error' | 'info', duration = 4500) {
  if (toastTimer) clearTimeout(toastTimer)
  toastMessage.value = message
  toastType.value = type
  if (duration > 0) {
    toastTimer = setTimeout(() => {
      toastMessage.value = ''
      toastTimer = null
    }, duration)
  }
}

function closeToast() {
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = null
  toastMessage.value = ''
}

function delay(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

async function waitForVoiceRevision(revision: string, timeoutMs = 60000) {
  const generation = ++waitGeneration
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline && generation === waitGeneration) {
    try {
      const status = await apiGet<{ voice_connected?: boolean; voice_config_revision?: string }>('/voice/status')
      if (status.voice_connected && status.voice_config_revision === revision) return
    } catch {
      // A short connection failure is expected while Voice is restarting.
    }
    await delay(1000)
  }
  if (generation !== waitGeneration) throw new Error('等待已取消')
  throw new Error('Voice 未在 60 秒内恢复，请检查 Voice 服务日志')
}

async function persistSettings(apply: boolean) {
  if (apply) applying.value = true
  else saving.value = true
  error.value = ''
  try {
    const result = await apiPut<SettingsPayload>('/admin/settings', { values: draft.value, apply })
    hydrate(result)
    if (!apply) {
      showToast('配置已保存', 'success')
      return
    }

    await loadAppBranding()
    if (result.voice_restart_requested && result.voice_config_revision) {
      showToast('正在等待 Voice 重启', 'info', 0)
      await waitForVoiceRevision(result.voice_config_revision)
      showToast('已重启成功', 'success')
    } else if (result.backend_restart_required) {
      showToast('配置已应用，后端服务将在下次启动时使用新配置', 'success', 6500)
    } else {
      showToast('配置已应用', 'success')
    }
  } catch (e: any) {
    error.value = String(e?.message || e)
    showToast(error.value, 'error', 8000)
  } finally {
    if (apply) applying.value = false
    else saving.value = false
  }
}

async function saveConfig() {
  await persistSettings(false)
}

async function applyConfig() {
  await persistSettings(true)
}

function assetPreviewUrl(asset: ManagedAsset): string {
  if (!asset.url) return ''
  return `${apiUrl(asset.url)}?v=${asset.version}`
}

async function uploadAsset(asset: ManagedAsset, event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  assetBusy.value[asset.key] = true
  error.value = ''
  try {
    const result = await apiPutFile<{ voice_restart_requested?: boolean; voice_config_revision?: string }>(`/admin/assets/${asset.key}`, file)
    await load()
    if (asset.key === 'web-app-icon') await loadAppBranding()
    if (result.voice_restart_requested && result.voice_config_revision) {
      showToast('正在等待 Voice 重启', 'info', 0)
      await waitForVoiceRevision(result.voice_config_revision)
      showToast('已重启成功', 'success')
    } else {
      showToast('图片已上传并生效', 'success')
    }
  } catch (e: any) {
    error.value = String(e?.message || e)
    showToast(error.value, 'error', 8000)
  } finally {
    assetBusy.value[asset.key] = false
  }
}

async function clearAsset(asset: ManagedAsset) {
  assetBusy.value[asset.key] = true
  error.value = ''
  try {
    const result = await apiDelete<{ voice_restart_requested?: boolean; voice_config_revision?: string }>(`/admin/assets/${asset.key}`)
    await load()
    if (asset.key === 'web-app-icon') await loadAppBranding()
    if (result.voice_restart_requested && result.voice_config_revision) {
      showToast('正在等待 Voice 重启', 'info', 0)
      await waitForVoiceRevision(result.voice_config_revision)
      showToast('已重启成功', 'success')
    } else {
      showToast('图片已清除', 'success')
    }
  } catch (e: any) {
    error.value = String(e?.message || e)
    showToast(error.value, 'error', 8000)
  } finally {
    assetBusy.value[asset.key] = false
  }
}

function clearSecret(field: SettingField) {
  draft.value[field.key] = null
  field.configured = false
}

function selectGroup(group: string) {
  activeGroup.value = group
  error.value = ''
}

async function signOut() {
  await logout()
  await router.replace('/login')
}

onMounted(load)
onBeforeUnmount(() => {
  waitGeneration += 1
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <div class="theme-settings-shell h-full flex flex-col bg-gray-50">
    <header class="theme-settings-header bg-white border-b border-gray-200 px-4 md:px-7 py-3 flex flex-wrap items-center justify-between gap-3">
      <div class="min-w-0">
        <h1 class="text-xl font-bold text-gray-900 flex items-center gap-2">
          <ServerCog :size="22" class="text-blue-600" />
          设置
        </h1>
        <p class="text-sm text-gray-500 mt-1">按用途管理机器人、音乐账号和运行参数</p>
      </div>
      <div class="ml-auto flex flex-wrap items-center justify-end gap-2">
        <template v-if="activeGroup !== 'authorization'">
          <button class="btn-secondary settings-header-action" type="button" :disabled="loading || saving || applying" @click="saveConfig">
            <Save :size="17" />
            {{ saving ? '正在保存' : '保存配置' }}
          </button>
          <button class="btn-primary settings-header-action" type="button" :disabled="loading || saving || applying" @click="applyConfig">
            <RefreshCw :size="17" :class="applying ? 'animate-spin' : ''" />
            {{ applying ? '正在应用' : '应用配置' }}
          </button>
        </template>
        <RouterLink v-if="!DEMO_MODE" to="/change-password" class="p-2 text-gray-500 hover:text-blue-600" title="修改管理员密码">
          <KeyRound :size="19" />
        </RouterLink>
        <button v-if="!DEMO_MODE" class="p-2 text-gray-500 hover:text-red-600" title="退出管理员登录" @click="signOut">
          <LogOut :size="19" />
        </button>
      </div>
    </header>

    <div class="flex-1 min-h-0 flex flex-col md:flex-row">
      <nav class="theme-settings-nav bg-white border-b md:border-b-0 md:border-r border-gray-200 md:w-56 p-3 overflow-x-auto md:overflow-y-auto flex md:block gap-1">
        <div v-for="section in NAV_SECTIONS" :key="section.id" class="contents md:block md:mb-4">
          <p class="hidden md:block px-3 pt-2 pb-2 text-xs font-semibold text-gray-400">{{ section.label }}</p>
          <button
            v-for="group in section.groups"
            :key="group.id"
            type="button"
            :aria-current="activeGroup === group.id ? 'page' : undefined"
            :class="['whitespace-nowrap w-auto md:w-full text-left px-3 py-2.5 rounded-md text-sm font-medium transition-colors', activeGroup === group.id ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-100']"
            @click="selectGroup(group.id)"
          >
            <span class="block">{{ group.label }}</span>
            <span class="hidden md:block mt-1 text-xs font-normal opacity-70">{{ group.summary }}</span>
          </button>
        </div>
      </nav>

      <main class="theme-settings-workspace flex-1 overflow-y-auto px-4 md:px-8 py-6 pb-8">
        <div class="max-w-3xl mx-auto">
          <div v-if="loading" class="py-20 text-center text-gray-500">正在加载配置...</div>
          <template v-else-if="payload">
            <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
              <h2 class="text-lg font-semibold text-gray-900">{{ activeCategory.label }}</h2>
              <span v-if="activeNeedsVoiceRestart" class="theme-settings-restart text-xs px-2 py-1 rounded bg-amber-50 text-amber-700 border border-amber-200">应用时自动重启 Voice</span>
            </div>
            <p class="mb-6 text-sm leading-6 text-gray-500">{{ activeCategory.description }}</p>

            <p v-if="DEMO_MODE && activeGroup === 'authorization'" class="text-sm text-gray-500">在线体验不提供账号登录，也不接收 Cookie、Token 或密码。部署后可在这里管理音乐平台授权。</p>
            <CookieView v-else-if="activeGroup === 'authorization'" embedded />

            <section v-if="activeAssets.length" class="theme-settings-panel bg-white border border-gray-200 rounded-lg divide-y divide-gray-100 mb-6">
              <div v-for="asset in activeAssets" :key="asset.key" class="p-4 md:p-5 grid md:grid-cols-[240px_minmax(0,1fr)] gap-3 md:gap-6 items-center">
                <div>
                  <div class="text-sm font-medium text-gray-800">{{ asset.label }}</div>
                  <p class="text-xs text-gray-500 mt-1">{{ asset.help }}</p>
                  <p class="text-xs text-gray-400 mt-1 font-mono break-all">{{ asset.storage_path }}</p>
                </div>
                <div class="flex flex-wrap items-center gap-3 min-w-0">
                  <div class="w-14 h-14 flex-shrink-0 border border-gray-200 rounded-md bg-gray-50 overflow-hidden flex items-center justify-center text-gray-400">
                    <img v-if="asset.configured" :src="assetPreviewUrl(asset)" :alt="asset.label" class="w-full h-full object-contain" />
                    <ImageIcon v-else :size="22" />
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="text-sm text-gray-700">{{ asset.configured ? '已上传' : '尚未上传' }}</div>
                    <div class="text-xs text-gray-500 mt-1">PNG、JPEG、WebP、GIF，最大 {{ asset.max_size_mb }} MiB</div>
                  </div>
                  <div class="flex items-center gap-2">
                    <label :class="['btn-secondary cursor-pointer', assetBusy[asset.key] ? 'opacity-50 pointer-events-none' : '']">
                      <Upload :size="17" />
                      {{ asset.configured ? '更换' : '上传' }}
                      <input type="file" class="sr-only" :accept="asset.accept" :disabled="assetBusy[asset.key]" @change="uploadAsset(asset, $event)" />
                    </label>
                    <button v-if="asset.configured" type="button" class="p-2 text-gray-500 hover:text-red-600" :disabled="assetBusy[asset.key]" title="清除图片" @click="clearAsset(asset)">
                      <Trash2 :size="18" />
                    </button>
                  </div>
                </div>
              </div>
            </section>

            <section v-if="activeFields.length" class="theme-settings-panel bg-white border border-gray-200 rounded-lg divide-y divide-gray-100">
              <div v-for="field in activeFields" :key="field.key" class="p-4 md:p-5 grid md:grid-cols-[240px_minmax(0,1fr)] gap-2 md:gap-6 items-center">
                <div>
                  <label :for="field.key" class="text-sm font-medium text-gray-800">{{ field.label }}</label>
                  <p v-if="field.help || FIELD_HELP[field.key]" class="text-xs leading-5 text-gray-500 mt-1">{{ field.help || FIELD_HELP[field.key] }}</p>
                  <p v-if="field.sensitive && field.configured" class="text-xs text-green-600 mt-1 flex items-center gap-1"><Check :size="12" /> 已配置</p>
                </div>

                <label v-if="field.type === 'boolean'" class="inline-flex items-center gap-3 cursor-pointer">
                  <input v-model="draft[field.key]" type="checkbox" class="w-4 h-4 accent-blue-600" />
                  <span class="text-sm text-gray-600">{{ draft[field.key] ? '启用' : '停用' }}</span>
                </label>

                <select v-else-if="field.type === 'select'" :id="field.key" v-model="draft[field.key]" class="input-field w-full">
                  <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
                </select>

                <textarea v-else-if="field.type === 'multiline'" :id="field.key" v-model="draft[field.key]" rows="4" class="input-field w-full resize-y" />

                <div v-else-if="field.sensitive" class="flex gap-2 min-w-0">
                  <div class="relative flex-1 min-w-0">
                    <input
                      :id="field.key"
                      v-model="draft[field.key]"
                      :type="revealed[field.key] ? 'text' : 'password'"
                      :placeholder="field.configured ? '留空表示保持当前值' : '尚未配置'"
                      autocomplete="new-password"
                      :disabled="DEMO_MODE"
                      class="input-field w-full pr-10 font-mono text-sm"
                    />
                    <button type="button" class="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700" :title="revealed[field.key] ? '隐藏' : '显示'" @click="revealed[field.key] = !revealed[field.key]">
                      <EyeOff v-if="revealed[field.key]" :size="17" />
                      <Eye v-else :size="17" />
                    </button>
                  </div>
                  <button v-if="field.configured" type="button" class="px-3 text-sm text-red-600 hover:bg-red-50 rounded-md" @click="clearSecret(field)">清除</button>
                </div>

                <input
                  v-else
                  :id="field.key"
                  v-model="draft[field.key]"
                  :type="field.type === 'integer' ? 'number' : field.type === 'url' ? 'url' : 'text'"
                  :min="field.minimum ?? undefined"
                  :max="field.maximum ?? undefined"
                  class="input-field w-full"
                />
              </div>
            </section>

            <section v-if="activeGroup === 'backend'" class="mt-6 border-t border-gray-200 pt-5">
              <h3 class="text-sm font-semibold text-gray-800 mb-3">启动配置（只读）</h3>
              <dl class="grid sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
                <div v-for="(value, key) in payload.bootstrap" :key="key" class="min-w-0">
                  <dt class="text-gray-500">{{ key }}</dt>
                  <dd class="text-gray-800 font-mono break-all mt-0.5">{{ value }}</dd>
                </div>
              </dl>
            </section>

          </template>
          <p v-if="error && !payload" class="text-red-600">{{ error }}</p>
        </div>
      </main>
    </div>
    <FloatingToast :message="toastMessage" :type="toastType" @close="closeToast" />
  </div>
</template>
