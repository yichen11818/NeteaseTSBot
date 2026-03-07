<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { apiGet, apiPost } from '../api'
import { 
  X, 
  QrCode, 
  User, 
  LogIn, 
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Loader2
} from 'lucide-vue-next'

const props = defineProps<{
  isVisible: boolean
}>()

const emit = defineEmits<{
  close: []
  loginSuccess: [userInfo: any]
}>()

const loginStatus = ref<'idle' | 'qr_loading' | 'qr_waiting' | 'qr_scanning' | 'success' | 'error'>('idle')
const qrUrl = ref('')
const qrKey = ref('')
const ptqrtoken = ref('')
const ptLoginSig = ref('')
const errorMessage = ref('')
const userInfo = ref<any>(null)
const cookieInput = ref('')
const loginMethod = ref<'qr' | 'cookie'>('qr')
const statusCheckInterval = ref<number | null>(null)

const adminToken = ref('')

// Check current login status
async function checkLoginStatus() {
  try {
    const status = await apiGet<any>('/qqmusic/login/status')
    if (status.logged_in) {
      loginStatus.value = 'success'
      userInfo.value = { uin: status.uin }
      emit('loginSuccess', userInfo.value)
    }
  } catch (e) {
    // Not logged in, which is fine
  }
}

// Start QR code login
async function startQRLogin() {
  loginStatus.value = 'qr_loading'
  errorMessage.value = ''
  
  try {
    console.log('Starting QR login...')
    const result = await apiGet<any>('/qqmusic/login/qr/key')
    console.log('QR Key Result:', result)
    
    if (result.qr_image_base64) {
      qrUrl.value = `data:image/png;base64,${result.qr_image_base64}`
    } else {
      qrUrl.value = result.qr_url
    }
    qrKey.value = result.qr_key
    ptqrtoken.value = result.ptqrtoken
    ptLoginSig.value = result.pt_login_sig
    loginStatus.value = 'qr_waiting'
    
    console.log('QR URL:', result.qr_url)
    console.log('QR Key:', result.qr_key)
    console.log('PTQRToken:', result.ptqrtoken)
    console.log('PTLoginSig:', result.pt_login_sig)
    
    // Start polling for login status
    startStatusPolling()
  } catch (e: any) {
    console.error('QR login failed:', e)
    loginStatus.value = 'error'
    errorMessage.value = String(e?.message ?? e)
  }
}

// Start polling QR code status
function startStatusPolling() {
  if (statusCheckInterval.value) {
    clearInterval(statusCheckInterval.value)
  }
  
  statusCheckInterval.value = window.setInterval(async () => {
    try {
      const result = await apiGet<any>(`/qqmusic/login/qr/check?qr_key=${qrKey.value}&ptqrtoken=${ptqrtoken.value}&pt_login_sig=${ptLoginSig.value}`)
      
      console.log('QR Status Check Result:', result)
      
      if (result.status === 'scanning') {
        console.log('QR Code is being scanned')
        loginStatus.value = 'qr_scanning'
      } else if (result.status === 'success') {
        console.log('Login successful!', result)
        stopStatusPolling()
        
        // Handle successful login with authorization info
        if (result.uin) {
          userInfo.value = { uin: result.uin }
          console.log('Got UIN:', result.uin)
          
          // If we have sigx, we could potentially get full cookies
          if (result.sigx) {
            console.log('Login successful with sigx:', result.sigx)
            // TODO: Use sigx to get QQ Music cookies
          }
          
          if (result.auth_url) {
            console.log('Auth URL:', result.auth_url)
            try {
              const token = adminToken.value.trim()
              const headers: Record<string, string> = {}
              if (token) headers['x-admin-token'] = token
              await apiPost('/qqmusic/login/qr/confirm', { auth_url: result.auth_url }, headers)
              // Re-check status after confirm
              const st = await apiGet<any>('/qqmusic/login/status')
              if (st.logged_in) {
                userInfo.value = { uin: st.uin || result.uin }
              }
            } catch (e: any) {
              console.error('QR confirm failed:', e)
            }
          }
        } else {
          userInfo.value = { uin: 'QQ用户' }
        }
        
        loginStatus.value = 'success'
        emit('loginSuccess', userInfo.value)
      } else if (result.status === 'expired') {
        console.log('QR Code expired')
        loginStatus.value = 'error'
        errorMessage.value = '二维码已过期，请重新获取'
        stopStatusPolling()
      } else if (result.status === 'error') {
        console.log('Login error:', result.message)
        loginStatus.value = 'error'
        errorMessage.value = result.message || '登录失败'
        stopStatusPolling()
      } else if (result.status === 'waiting') {
        console.log('Still waiting for scan...')
        // Continue polling
      } else {
        console.log('Unknown status:', result.status, result)
      }
    } catch (e: any) {
      console.error('Status check failed:', e)
      // Don't stop polling on network errors, just log them
    }
  }, 2000)
}

// Stop polling
function stopStatusPolling() {
  if (statusCheckInterval.value) {
    clearInterval(statusCheckInterval.value)
    statusCheckInterval.value = null
  }
}

// Login with cookie
async function loginWithCookie() {
  if (!cookieInput.value.trim()) {
    errorMessage.value = '请输入Cookie'
    return
  }
  
  loginStatus.value = 'qr_loading'
  errorMessage.value = ''
  
  try {
    await apiPost('/qqmusic/login/cookie', { cookie: cookieInput.value })
    
    // Get user info
    try {
      const info = await apiGet<any>('/qqmusic/user/info')
      userInfo.value = info
    } catch (e) {
      userInfo.value = { uin: 'Unknown' }
    }
    
    loginStatus.value = 'success'
    emit('loginSuccess', userInfo.value)
  } catch (e: any) {
    loginStatus.value = 'error'
    errorMessage.value = String(e?.message ?? e)
  }
}

// Refresh login
async function refreshLogin() {
  try {
    const result = await apiPost<any>('/qqmusic/login/refresh', {})
    if (result.success) {
      loginStatus.value = 'success'
    } else {
      loginStatus.value = 'error'
      errorMessage.value = result.message
    }
  } catch (e: any) {
    loginStatus.value = 'error'
    errorMessage.value = String(e?.message ?? e)
  }
}

// Close modal
function closeModal() {
  stopStatusPolling()
  emit('close')
}

// Lifecycle
onMounted(() => {
  checkLoginStatus()
})

onUnmounted(() => {
  stopStatusPolling()
})
</script>

<template>
  <div 
    v-if="isVisible" 
    class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
    @click.self="closeModal"
  >
    <div class="bg-white rounded-2xl shadow-2xl max-w-md w-full max-h-[90vh] overflow-y-auto">
      <!-- Header -->
      <div class="flex items-center justify-between p-6 border-b border-gray-200">
        <h2 class="text-xl font-bold text-gray-900 flex items-center gap-2">
          <LogIn :size="24" class="text-blue-600" />
          QQ音乐登录
        </h2>
        <button
          @click="closeModal"
          class="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <X :size="20" class="text-gray-500" />
        </button>
      </div>

      <div class="px-6 pt-4">
        <label class="block text-sm font-medium text-gray-700 mb-2">管理员 Token</label>
        <input
          v-model="adminToken"
          type="password"
          placeholder="用于保存QQ cookie到服务器（不会存到浏览器）"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
        />
      </div>

      <!-- Content -->
      <div class="p-6">
        <!-- Login method selector -->
        <div class="mb-6">
          <div class="flex bg-gray-100 rounded-lg p-1">
            <button
              @click="loginMethod = 'qr'"
              :class="[
                'flex-1 px-3 py-2 text-sm font-medium rounded-md transition-all duration-200',
                loginMethod === 'qr' 
                  ? 'bg-white text-blue-600 shadow-sm' 
                  : 'text-gray-600 hover:text-gray-900'
              ]"
            >
              <QrCode :size="16" class="inline mr-2" />
              二维码登录
            </button>
            <button
              @click="loginMethod = 'cookie'"
              :class="[
                'flex-1 px-3 py-2 text-sm font-medium rounded-md transition-all duration-200',
                loginMethod === 'cookie' 
                  ? 'bg-white text-blue-600 shadow-sm' 
                  : 'text-gray-600 hover:text-gray-900'
              ]"
            >
              <User :size="16" class="inline mr-2" />
              Cookie登录
            </button>
          </div>
        </div>

        <!-- QR Code Login -->
        <div v-if="loginMethod === 'qr'">
          <!-- Success State -->
          <div v-if="loginStatus === 'success'" class="text-center py-8">
            <CheckCircle :size="64" class="text-green-500 mx-auto mb-4" />
            <h3 class="text-lg font-semibold text-gray-900 mb-2">登录成功！</h3>
            <p class="text-gray-600 mb-4">
              用户: {{ userInfo?.uin || 'Unknown' }}
            </p>
            <button
              @click="closeModal"
              class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition-colors"
            >
              完成
            </button>
          </div>

          <!-- QR Code Display -->
          <div v-else-if="loginStatus === 'qr_waiting' || loginStatus === 'qr_scanning'" class="text-center">
            <div class="bg-white border-2 border-gray-200 rounded-xl p-4 mb-4 inline-block">
              <img :src="qrUrl" alt="QR Code" class="w-48 h-48" />
            </div>
            
            <div v-if="loginStatus === 'qr_waiting'" class="mb-4">
              <h3 class="text-lg font-semibold text-gray-900 mb-2">请扫描二维码</h3>
              <p class="text-gray-600">使用QQ手机版扫描上方二维码</p>
            </div>
            
            <div v-else-if="loginStatus === 'qr_scanning'" class="mb-4">
              <h3 class="text-lg font-semibold text-blue-600 mb-2 flex items-center justify-center gap-2">
                <Loader2 :size="20" class="animate-spin" />
                扫描成功，请确认登录
              </h3>
              <p class="text-gray-600">请在手机上确认登录</p>
            </div>

            <button
              @click="startQRLogin"
              class="text-blue-600 hover:text-blue-700 text-sm font-medium flex items-center gap-1 mx-auto"
            >
              <RefreshCw :size="16" />
              刷新二维码
            </button>
          </div>

          <!-- Initial State -->
          <div v-else-if="loginStatus === 'idle'" class="text-center py-8">
            <QrCode :size="64" class="text-gray-400 mx-auto mb-4" />
            <h3 class="text-lg font-semibold text-gray-900 mb-2">二维码登录</h3>
            <p class="text-gray-600 mb-6">扫描二维码快速登录QQ音乐</p>
            <button
              @click="startQRLogin"
              class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium transition-colors"
            >
              获取二维码
            </button>
          </div>

          <!-- Loading State -->
          <div v-else-if="loginStatus === 'qr_loading'" class="text-center py-8">
            <Loader2 :size="48" class="text-blue-600 mx-auto mb-4 animate-spin" />
            <h3 class="text-lg font-semibold text-gray-900 mb-2">正在获取二维码...</h3>
          </div>

          <!-- Error State -->
          <div v-else-if="loginStatus === 'error'" class="text-center py-8">
            <AlertCircle :size="64" class="text-red-500 mx-auto mb-4" />
            <h3 class="text-lg font-semibold text-gray-900 mb-2">登录失败</h3>
            <p class="text-red-600 mb-6">{{ errorMessage }}</p>
            <button
              @click="startQRLogin"
              class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium transition-colors"
            >
              重试
            </button>
          </div>
        </div>

        <!-- Cookie Login -->
        <div v-else-if="loginMethod === 'cookie'">
          <!-- Success State -->
          <div v-if="loginStatus === 'success'" class="text-center py-8">
            <CheckCircle :size="64" class="text-green-500 mx-auto mb-4" />
            <h3 class="text-lg font-semibold text-gray-900 mb-2">登录成功！</h3>
            <p class="text-gray-600 mb-4">
              用户: {{ userInfo?.uin || 'Unknown' }}
            </p>
            <button
              @click="closeModal"
              class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition-colors"
            >
              完成
            </button>
          </div>

          <!-- Cookie Input -->
          <div v-else>
            <div class="mb-4">
              <label class="block text-sm font-medium text-gray-700 mb-2">
                QQ音乐 Cookie
              </label>
              <textarea
                v-model="cookieInput"
                placeholder="请粘贴从浏览器获取的QQ音乐Cookie..."
                class="w-full h-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none text-sm"
              ></textarea>
              <p class="text-xs text-gray-500 mt-2">
                从浏览器开发者工具中复制QQ音乐的Cookie
              </p>
            </div>

            <!-- Error Message -->
            <div v-if="loginStatus === 'error'" class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
              <p class="text-red-600 text-sm">{{ errorMessage }}</p>
            </div>

            <button
              @click="loginWithCookie"
              :disabled="!cookieInput.trim() || loginStatus === 'qr_loading'"
              class="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white px-6 py-3 rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
            >
              <Loader2 v-if="loginStatus === 'qr_loading'" :size="16" class="animate-spin" />
              <span>{{ loginStatus === 'qr_loading' ? '登录中...' : '登录' }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Custom scrollbar for the modal */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>
