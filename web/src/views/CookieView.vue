<template>
  <div class="h-full flex flex-col bg-gray-50">
    <!-- Header -->
    <div class="bg-white/80 backdrop-blur-md border-b border-gray-200 px-6 py-4 sticky top-0 z-20 shadow-sm transition-all duration-300">
      <div class="flex items-center gap-4">
        <h1 class="text-2xl font-bold text-gray-900 tracking-tight flex items-center gap-2">
          <Settings :size="28" class="text-blue-600" />
          系统设置
        </h1>
        <span class="text-sm text-gray-500 hidden md:inline-block border-l border-gray-200 pl-4 h-5 leading-5">
          管理您的网易云音乐登录状态和系统配置
        </span>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-4 md:px-6 py-4 md:py-6 pb-24 scrollbar-thin">
      <div class="max-w-4xl mx-auto space-y-6 md:space-y-8 fade-in">
        <!-- Status Banner -->
        <div v-if="status" class="status-info animate-fade-in shadow-sm rounded-xl border-blue-100 bg-blue-50/50">
          <div class="flex-shrink-0">
            <Info :size="20" />
          </div>
          <span class="font-medium text-blue-700">{{ status }}</span>
        </div>

        <!-- User Login Section -->
        <section class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden relative">
          <div class="absolute top-0 right-0 p-6 opacity-[0.03] pointer-events-none">
            <User :size="200" class="text-black" />
          </div>
          
          <div class="p-5 md:p-8 relative z-10">
            <div class="flex items-center justify-between mb-6 md:mb-8">
              <div>
                <h2 class="text-xl font-bold text-gray-900 flex items-center gap-3">
                  用户登录
                  <span 
                    :class="[
                      'text-xs px-2.5 py-1 rounded-full font-semibold border transition-colors',
                      userCookie 
                        ? 'bg-green-50 text-green-700 border-green-200' 
                        : 'bg-gray-100 text-gray-600 border-gray-200'
                    ]"
                  >
                    {{ userCookie ? '已登录' : '未登录' }}
                  </span>
                </h2>
                <p class="text-gray-500 text-sm mt-2">登录以获取您的歌单和收藏列表（Cookie 存储在本地）</p>
              </div>
            </div>

            <div class="flex flex-col md:flex-row gap-8">
              <div class="flex-1 space-y-6">
                <div class="flex flex-wrap gap-3">
                  <button @click="startUserQr" class="btn-primary shadow-blue-200">
                    <QrCode :size="18" />
                    扫码登录
                  </button>
                  <button @click="load" class="btn-secondary">
                    <RefreshCw :size="18" />
                    刷新状态
                  </button>
                  <button 
                    v-if="userCookie" 
                    @click="clearUserCookie" 
                    class="btn-secondary text-red-600 hover:text-red-700 hover:bg-red-50 hover:border-red-200"
                  >
                    <LogOut :size="18" />
                    退出登录
                  </button>
                </div>
                
                <div v-if="userCookie" class="p-4 bg-gray-50/50 rounded-xl border border-gray-100 text-sm text-gray-500 break-all font-mono leading-relaxed">
                  <div class="flex items-center gap-2 mb-2 text-gray-700 font-medium">
                    <CheckCircle2 :size="14" class="text-green-500" />
                    Cookie 已保存
                  </div>
                  {{ userCookie.substring(0, 50) }}...
                </div>
              </div>

              <div 
                v-if="userQrImg" 
                class="flex-shrink-0 flex flex-col items-center gap-4 bg-white p-6 rounded-2xl border border-gray-200 shadow-lg shadow-gray-100 animate-scale-in"
              >
                <img :src="userQrImg" alt="user qr" class="w-48 h-48 object-contain rounded-lg" />
                <span class="text-sm text-gray-500 font-medium flex items-center gap-1.5">
                  <Smartphone :size="16" />
                  请使用网易云 App 扫码
                </span>
              </div>
            </div>
          </div>
        </section>

        <!-- Admin Login Section -->
        <section class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden relative">
          <div class="absolute top-0 right-0 p-6 opacity-[0.03] pointer-events-none">
            <Shield :size="200" class="text-black" />
          </div>

          <div class="p-5 md:p-8 relative z-10">
            <div class="flex items-center justify-between mb-6 md:mb-8">
              <div>
                <h2 class="text-xl font-bold text-gray-900 flex items-center gap-3">
                  后台播放授权
                  <span 
                    :class="[
                      'text-xs px-2.5 py-1 rounded-full font-semibold border transition-colors',
                      adminStatus 
                        ? 'bg-green-50 text-green-700 border-green-200' 
                        : 'bg-gray-100 text-gray-600 border-gray-200'
                    ]"
                  >
                    {{ adminStatus ? '已授权' : '未授权' }}
                  </span>
                </h2>
                <p class="text-gray-500 text-sm mt-2">用于服务器端播放音乐（Cookie 加密存储在服务器，不做返回）</p>
              </div>
            </div>

            <div class="space-y-8">
              <div class="flex flex-col md:flex-row gap-8">
                <div class="flex-1 space-y-6">
                  <div class="flex flex-wrap gap-3">
                    <button @click="startAdminQr" class="btn-primary shadow-blue-200">
                      <QrCode :size="18" />
                      扫码授权
                    </button>
                    <button @click="load" class="btn-secondary">
                      <RefreshCw :size="18" />
                      刷新状态
                    </button>
                  </div>
                  
                  <div v-if="adminStatus" class="flex items-center gap-2 text-sm text-green-600 font-medium">
                    <CheckCircle2 :size="16" />
                    服务器已配置有效 Cookie
                  </div>
                </div>

                <div 
                  v-if="adminQrImg" 
                  class="flex-shrink-0 flex flex-col items-center gap-4 bg-white p-6 rounded-2xl border border-gray-200 shadow-lg shadow-gray-100 animate-scale-in"
                >
                  <img :src="adminQrImg" alt="admin qr" class="w-48 h-48 object-contain rounded-lg" />
                  <span class="text-sm text-gray-500 font-medium flex items-center gap-1.5">
                    <Smartphone :size="16" />
                    请使用网易云 App 扫码
                  </span>
                </div>
              </div>

              <!-- Manual Cookie Input -->
              <div class="pt-8 border-t border-gray-100">
                <h3 class="text-sm font-bold text-gray-900 mb-4 flex items-center gap-2">
                  <Terminal :size="16" class="text-gray-400" />
                  手动配置
                </h3>
                <div class="flex flex-col md:flex-row gap-3">
                  <input 
                    v-model="adminManualCookie" 
                    type="text" 
                    placeholder="输入 Cookie 字符串 (MUSIC_U=...)" 
                    class="input-field flex-1 font-mono text-sm"
                  />
                  <input 
                    v-model="adminToken" 
                    type="password" 
                    placeholder="Admin Token (可选)" 
                    class="input-field md:w-48 font-mono text-sm"
                  />
                  <button @click="setAdminCookie" class="btn-secondary whitespace-nowrap font-medium">
                    保存配置
                  </button>
                </div>
                <p class="text-xs text-gray-400 mt-3 flex items-center gap-1.5">
                  <AlertCircle :size="12" />
                  如果扫码无法使用，您可以手动输入 Cookie。请确保 Cookie 包含 MUSIC_U 字段。
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiGet, apiPost } from '../api'
import { 
  Settings, 
  Info, 
  User, 
  QrCode, 
  RefreshCw, 
  LogOut, 
  CheckCircle2, 
  Smartphone, 
  Shield, 
  Terminal, 
  AlertCircle 
} from 'lucide-vue-next'

const USER_COOKIE_KEY = 'tsbot_user_netease_cookie'

const userCookie = ref(localStorage.getItem(USER_COOKIE_KEY) || '')
const userQrKey = ref('')
const userQrImg = ref('')

const adminStatus = ref<boolean>(false)
const adminQrKey = ref('')
const adminQrImg = ref('')

const adminManualCookie = ref('')
const adminToken = ref('')

const status = ref('')

let userTimer: number | null = null
let adminTimer: number | null = null

async function load() {
  status.value = ''
  userCookie.value = localStorage.getItem(USER_COOKIE_KEY) || ''
  const st = await apiGet<{ admin_cookie_set: boolean }>('/admin/status')
  adminStatus.value = !!st?.admin_cookie_set
}

async function setAdminCookie() {
  status.value = ''
  try {
    const cookie = adminManualCookie.value
    if (!cookie.trim()) throw new Error('cookie is empty')
    const headers: Record<string, string> = {}
    if (adminToken.value.trim()) headers['x-admin-token'] = adminToken.value.trim()
    await apiPost<any>('/admin/cookie', { cookie }, headers)
    adminManualCookie.value = ''
    status.value = 'admin cookie saved server-side'
    await load()
  } catch (e: any) {
    status.value = String(e?.message ?? e)
  }
}

function clearUserCookie() {
  localStorage.removeItem(USER_COOKIE_KEY)
  userCookie.value = ''
  status.value = 'cleared user cookie (localStorage)'
}

function stopUserPoll() {
  if (userTimer !== null) {
    clearInterval(userTimer)
    userTimer = null
  }
}

function stopAdminPoll() {
  if (adminTimer !== null) {
    clearInterval(adminTimer)
    adminTimer = null
  }
}

async function startUserQr() {
  status.value = ''
  try {
    stopUserPoll()
    userQrImg.value = ''
    const keyRes = await apiGet<any>('/netease/qr/key')
    const key = keyRes?.data?.unikey || keyRes?.data?.key || keyRes?.unikey
    userQrKey.value = String(key || '')
    if (!userQrKey.value) throw new Error('failed to get qr key')

    const createRes = await apiGet<any>(`/netease/qr/create?key=${encodeURIComponent(userQrKey.value)}`)
    userQrImg.value = String(createRes?.data?.qrimg || '')

    status.value = 'user qr created'
    userTimer = window.setInterval(checkUserQr, 1500)
  } catch (e: any) {
    status.value = String(e?.message ?? e)
  }
}

async function checkUserQr() {
  status.value = ''
  try {
    if (!userQrKey.value) return
    const r = await apiGet<any>(`/netease/qr/check?key=${encodeURIComponent(userQrKey.value)}`)
    const code = Number(r?.code)
    if (code === 803) {
      const cookie = String(r?.cookie || '')
      if (!cookie) throw new Error('authorized but cookie is empty')
      localStorage.setItem(USER_COOKIE_KEY, cookie)
      userCookie.value = cookie
      status.value = 'user authorized'
      stopUserPoll()
      return
    }
    if (code === 800) {
      status.value = 'user qr expired'
      stopUserPoll()
      return
    }
    if (code === 802) {
      status.value = 'user qr scanned'
      return
    }
    if (code === 801) {
      status.value = 'user qr waiting'
      return
    }
    status.value = `user qr unknown: code=${code}`
  } catch (e: any) {
    status.value = String(e?.message ?? e)
  }
}

async function startAdminQr() {
  status.value = ''
  try {
    stopAdminPoll()
    adminQrImg.value = ''
    const keyRes = await apiGet<any>('/admin/qr/key')
    const key = keyRes?.data?.unikey || keyRes?.data?.key || keyRes?.unikey
    adminQrKey.value = String(key || '')
    if (!adminQrKey.value) throw new Error('failed to get admin qr key')

    const createRes = await apiGet<any>(`/admin/qr/create?key=${encodeURIComponent(adminQrKey.value)}`)
    adminQrImg.value = String(createRes?.data?.qrimg || '')

    status.value = 'admin qr created'
    adminTimer = window.setInterval(checkAdminQr, 1500)
  } catch (e: any) {
    status.value = String(e?.message ?? e)
  }
}

async function checkAdminQr() {
  status.value = ''
  try {
    if (!adminQrKey.value) return
    const r = await apiGet<any>(`/admin/qr/check?key=${encodeURIComponent(adminQrKey.value)}`)
    const code = Number(r?.code)
    if (code === 803) {
      status.value = 'admin authorized (cookie saved server-side)'
      stopAdminPoll()
      await load()
      return
    }
    if (code === 800) {
      status.value = 'admin qr expired'
      stopAdminPoll()
      return
    }
    if (code === 802) {
      status.value = 'admin qr scanned'
      return
    }
    if (code === 801) {
      status.value = 'admin qr waiting'
      return
    }
    status.value = `admin qr unknown: code=${code}`
  } catch (e: any) {
    status.value = String(e?.message ?? e)
  }
}

onMounted(load)
</script>
