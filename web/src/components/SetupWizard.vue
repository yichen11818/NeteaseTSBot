<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowLeft, ArrowRight, Check, AlertCircle, Loader2, RefreshCw } from 'lucide-vue-next'
import { apiGet, apiPut } from '../api'
import { DEMO_MODE } from '../demoMode'
import type { DiagnosticReport, SetupSettings } from '../types/settings'

const emit = defineEmits<{ saved: [] }>()

const steps = ['连接 TeamSpeak', '选择音乐源', '应用并检查']
const step = ref(0)
const settings = ref<SetupSettings | null>(null)
const values = ref<Record<string, unknown>>({})
const busy = ref(false)
const error = ref('')
const message = ref('')
const report = ref<DiagnosticReport | null>(null)
let active = true
const teamspeakKeys = ['voice.ts3_host', 'voice.ts3_port', 'voice.ts3_nickname', 'voice.ts3_channel_id', 'voice.ts3_channel_path', 'voice.ts3_server_password', 'voice.ts3_channel_password']
const visibleFields = computed(() => settings.value?.fields.filter(field => step.value === 0 ? teamspeakKeys.includes(field.key) : field.key === 'backend.netease_api_base') || [])

function hydrate(result: SetupSettings) {
  settings.value = result
  values.value = Object.fromEntries(result.fields.filter(field => teamspeakKeys.includes(field.key) || field.key === 'backend.netease_api_base').map(field => [field.key, field.sensitive ? '' : field.value]))
}
onMounted(async () => {
  busy.value = true
  try { hydrate(await apiGet<SetupSettings>('/admin/settings')) }
  catch (e) { error.value = e instanceof Error ? e.message : '无法加载配置' }
  finally { busy.value = false }
})
onBeforeUnmount(() => { active = false })

async function saveStep() {
  busy.value = true; error.value = ''; message.value = ''; report.value = null
  try {
    const selected = Object.fromEntries(visibleFields.value.map(field => [field.key, values.value[field.key]]))
    hydrate(await apiPut<SetupSettings>('/admin/settings', { values: selected, apply: false }))
    emit('saved')
    step.value += 1
  } catch (e) { error.value = e instanceof Error ? e.message : '配置保存失败' }
  finally { busy.value = false }
}
async function runDiagnostics() {
  busy.value = true; error.value = ''; report.value = null
  try { report.value = await apiGet<DiagnosticReport>('/admin/diagnostics') }
  catch (e) { error.value = e instanceof Error ? e.message : '连接检查失败，请确认后端可访问并重新登录' }
  finally { busy.value = false }
}
async function applyAndCheck() {
  busy.value = true; error.value = ''; message.value = ''; report.value = null
  try {
    const result = await apiPut<SetupSettings>('/admin/settings', { values: {}, apply: true })
    hydrate(result)
    emit('saved')
    if (result.voice_restart_requested && result.voice_config_revision) {
      message.value = '配置已应用，等待 Voice 使用新配置重启…'
      const deadline = Date.now() + 60000
      let restored = false
      while (active && Date.now() < deadline) {
        try {
          const status = await apiGet<{ voice_connected: boolean; voice_config_revision: string }>('/voice/status')
          if (status.voice_connected && status.voice_config_revision === result.voice_config_revision) { restored = true; break }
        } catch { /* Voice can briefly go offline during restart. */ }
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
      if (!active) return
      if (!restored) throw new Error('Voice 未在 60 秒内使用新配置恢复。请检查容器或 Voice 日志，再重新检查连接。')
    }
    message.value = DEMO_MODE ? '模拟配置已应用。下面的结果仅用于体验。' : '配置已应用。连接检查不能代替实际播放，请最后点播一首可用曲目。'
    report.value = await apiGet<DiagnosticReport>('/admin/diagnostics')
  } catch (e) { message.value = ''; error.value = e instanceof Error ? e.message : '应用配置失败' }
  finally { busy.value = false }
}
</script>

<template>
  <section class="theme-setup-shell" aria-label="部署向导">
    <div>
      <h2 class="text-2xl font-bold text-gray-900 md:text-3xl">让机器人加入你的频道</h2>
      <p class="mt-2 text-sm leading-6 text-gray-500">准备好 TeamSpeak 地址，按顺序配置并检查连接。</p>

      <ol class="my-8 flex gap-3 border-b border-gray-200 pb-5 md:gap-6" aria-label="配置进度">
        <li v-for="(label, index) in steps" :key="label" :aria-current="step === index ? 'step' : undefined" class="flex flex-1 items-center gap-2 text-xs md:text-sm" :class="index <= step ? 'font-semibold text-blue-700' : 'text-gray-400'">
          <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full" :class="index <= step ? 'bg-blue-600 text-white' : 'bg-gray-200'">{{ index + 1 }}</span>{{ label }}
        </li>
      </ol>
      <p v-if="error" role="alert" class="mb-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{{ error }}</p>
      <p v-if="message" role="status" class="mb-5 text-sm leading-6 text-blue-700">{{ message }}</p>
      <p v-if="!settings && busy" class="py-12 text-gray-500">正在加载配置…</p>
      <template v-if="settings">
        <h3 class="text-lg font-semibold text-gray-900">{{ steps[step] }}</h3>
        <p v-if="step === 0" class="mt-2 text-sm leading-6 text-gray-500">填写语音服务器端口（通常为 9987）。频道 ID 或路径选填其一；都留空则使用默认频道。</p>
        <div v-if="step < 2" class="mt-6 space-y-5">
          <div v-for="field in visibleFields" :key="field.key">
            <label :for="`setup-${field.key}`" class="mb-1.5 block text-sm font-medium text-gray-800">{{ field.label }}</label>
            <input :id="`setup-${field.key}`" v-model="values[field.key]" :type="field.sensitive ? 'password' : field.type === 'integer' ? 'number' : field.type === 'url' ? 'url' : 'text'" :min="field.minimum ?? undefined" :max="field.maximum ?? undefined" :disabled="busy || (DEMO_MODE && field.sensitive)" :placeholder="field.sensitive && field.configured ? '已配置，留空保持原值' : ''" :autocomplete="field.sensitive ? 'new-password' : 'off'" class="input-field w-full disabled:opacity-50" />
          </div>
          <div v-if="step === 1" class="space-y-3 border-t border-gray-200 pt-5 text-sm leading-6 text-gray-600">
            <p>网易云音乐需要单独部署 NeteaseCloudMusicApi。暂时不用网易云，可以保留地址并跳过；连接检查会单独显示其状态。</p>
            <p>QQ 音乐和 B 站适配已内建，部分功能需要平台登录态。</p>
            <RouterLink v-if="!DEMO_MODE" to="/settings?group=authorization" class="inline-block font-medium text-blue-600 underline underline-offset-4">管理音乐平台登录 ↗</RouterLink>
            <p v-else>在线体验不接收账号、Cookie 或密码。</p>
          </div>
        </div>
        <div v-else class="mt-5">
          <p class="text-sm leading-6 text-gray-500">前两步只保存配置。点击“应用并检查”后，TeamSpeak 改动会自动重启 Voice；结果会分别列出后端、语音服务与音乐接口状态。</p>
          <div class="mt-5 flex flex-wrap gap-3">
            <button type="button" class="btn-primary gap-2" :disabled="busy" @click="applyAndCheck"><Loader2 v-if="busy" :size="16" class="animate-spin" /><Check v-else :size="16" />应用并检查</button>
            <button type="button" class="btn-secondary gap-2" :disabled="busy" @click="runDiagnostics"><RefreshCw :size="16" />重新检查连接</button>
          </div>
          <section v-if="report" class="mt-7" aria-label="连接检查结果" aria-live="polite">
            <h4 class="font-semibold text-gray-900">{{ report.demo ? '模拟检查结果' : report.ready ? '必要连接已就绪' : '还有连接需要处理' }}</h4>
            <ul class="mt-3 divide-y divide-gray-200">
              <li v-for="item in report.checks" :key="item.id" class="flex gap-3 py-4">
                <Check v-if="item.status === 'success'" :size="19" class="mt-0.5 shrink-0 text-green-600" />
                <AlertCircle v-else :size="19" class="mt-0.5 shrink-0" :class="item.status === 'error' ? 'text-red-600' : 'text-amber-600'" />
                <div class="min-w-0 text-sm"><div class="font-semibold text-gray-800">{{ item.label }} <span class="ml-1 font-normal text-gray-500">{{ item.status === 'success' ? '正常' : item.status === 'error' ? '失败' : '待处理' }}</span></div><p class="mt-1 leading-6 text-gray-500">{{ item.detail }}</p><p v-if="item.action" class="mt-1 leading-6 text-gray-700">{{ item.action }}</p><RouterLink v-if="item.status !== 'success' && item.group" :to="`/settings?group=${item.group}`" class="mt-1 inline-block text-blue-600 underline">查看对应配置</RouterLink></div>
              </li>
            </ul>
            <RouterLink to="/search" class="mt-5 inline-flex items-center gap-2 font-semibold text-blue-600">去点播第一首歌 <ArrowRight :size="17" /></RouterLink>
          </section>
        </div>
        <div class="mt-8 flex justify-between border-t border-gray-200 pt-5">
          <button type="button" class="btn-secondary gap-2" :disabled="step === 0 || busy" @click="step -= 1; error = ''; message = ''"><ArrowLeft :size="16" />上一步</button>
          <button v-if="step < 2" type="button" class="btn-primary gap-2" :disabled="busy" @click="saveStep"><Loader2 v-if="busy" :size="16" class="animate-spin" />保存并继续 <ArrowRight v-if="!busy" :size="16" /></button>
        </div>
      </template>
    </div>
  </section>
</template>
