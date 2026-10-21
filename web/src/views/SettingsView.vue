<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Check, Eye, EyeOff, Image as ImageIcon, KeyRound, LogOut, RefreshCw, Save, ServerCog, Trash2, Upload } from 'lucide-vue-next'
import { apiDelete, apiGet, apiPut, apiPutFile, apiUrl } from '../api'
import { logout } from '../auth'
import { loadAppBranding } from '../appConfig'
import FloatingToast from '../components/FloatingToast.vue'
import CookieView from './CookieView.vue'
import SetupWizard from '../components/SetupWizard.vue'
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
  ['setup', '部署向导'],
  ['web', 'Web 配置'],
  ['backend', 'Voice 服务'],
  ['music', '音乐接口配置'],
  ['authorization', '音乐会员登录'],
  ['teamspeak', 'TeamSpeak 配置'],
  ['serverquery', 'ServerQuery 兼容'],
  ['access', '外部 api'],
] as const

const GROUP_ALIASES: Record<string, string> = {
  description: 'teamspeak',
  voice: 'backend',
}

const router = useRouter()
const route = useRoute()
const payload = ref<SettingsPayload | null>(null)
const rawRequestedGroup = String(route.query.group || '')
const requestedGroup = GROUP_ALIASES[rawRequestedGroup] || rawRequestedGroup
const activeGroup = ref(GROUPS.some((group) => group[0] === requestedGroup) ? requestedGroup : 'web')
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

const activeFields = computed(() => payload.value?.fields.filter((field) => field.group === activeGroup.value) || [])
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

async function refreshAfterSetup() {
  try {
    hydrate(await apiGet<SettingsPayload>('/admin/settings'))
  } catch (e: any) {
    showToast(String(e?.message || e), 'error', 8000)
  }
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
          系统配置
        </h1>
        <p class="text-sm text-gray-500 mt-1">运行配置与服务连接</p>
      </div>
      <div class="ml-auto flex flex-wrap items-center justify-end gap-2">
        <template v-if="activeGroup !== 'authorization' && activeGroup !== 'setup'">
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
        <button
          v-for="group in GROUPS"
          :key="group[0]"
          type="button"
          :class="['whitespace-nowrap w-auto md:w-full text-left px-3 py-2.5 rounded-md text-sm font-medium transition-colors', activeGroup === group[0] ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-100']"
          @click="selectGroup(group[0])"
        >
          {{ group[1] }}
        </button>
      </nav>

      <main class="theme-settings-workspace flex-1 overflow-y-auto px-4 md:px-8 py-6 pb-8">
        <div class="max-w-3xl mx-auto">
          <div v-if="loading" class="py-20 text-center text-gray-500">正在加载配置...</div>
          <template v-else-if="payload">
            <SetupWizard v-if="activeGroup === 'setup'" @saved="refreshAfterSetup" />
            <template v-else>
              <div class="flex items-center justify-between mb-6">
                <h2 class="text-lg font-semibold text-gray-900">{{ GROUPS.find((item) => item[0] === activeGroup)?.[1] }}</h2>
                <span v-if="activeNeedsVoiceRestart" class="theme-settings-restart text-xs px-2 py-1 rounded bg-amber-50 text-amber-700 border border-amber-200">应用时自动重启 Voice</span>
              </div>

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
                    <p v-if="field.help" class="text-xs text-gray-500 mt-1">{{ field.help }}</p>
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
          </template>
          <p v-if="error && !payload" class="text-red-600">{{ error }}</p>
        </div>
      </main>
    </div>
    <FloatingToast :message="toastMessage" :type="toastType" @close="closeToast" />
  </div>
</template>
