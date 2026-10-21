<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { KeyRound, Save } from 'lucide-vue-next'
import { changePassword } from '../auth'
import { authState } from '../auth'

const router = useRouter()
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const submitting = ref(false)

async function submit() {
  error.value = ''
  if (newPassword.value !== confirmPassword.value) {
    error.value = '两次输入的新密码不一致'
    return
  }
  submitting.value = true
  try {
    await changePassword(currentPassword.value, newPassword.value)
    await router.replace('/settings')
  } catch (e: any) {
    error.value = String(e?.message || e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="theme-auth-shell min-h-[100dvh] bg-gray-50 flex items-center justify-center px-4 py-10">
    <section class="theme-auth-panel w-full max-w-md bg-white border border-gray-200 rounded-lg shadow-sm p-7">
      <div class="flex items-center gap-3 mb-7">
        <div class="w-10 h-10 rounded-lg bg-amber-500 text-white flex items-center justify-center">
          <KeyRound :size="21" />
        </div>
        <div>
          <h1 class="text-xl font-bold text-gray-900">{{ authState.must_change_password ? '设置管理员密码' : '修改管理员密码' }}</h1>
          <p class="text-sm text-gray-500">{{ authState.must_change_password ? '首次登录必须更换初始密码' : '修改后其他登录会话将失效' }}</p>
        </div>
      </div>
      <form class="space-y-5" @submit.prevent="submit">
        <input type="text" name="username" value="admin" autocomplete="username" class="sr-only" tabindex="-1" aria-hidden="true" />
        <label class="block">
          <span class="block text-sm font-medium text-gray-700 mb-1.5">当前密码</span>
          <input v-model="currentPassword" type="password" autocomplete="current-password" class="input-field w-full" required autofocus />
        </label>
        <label class="block">
          <span class="block text-sm font-medium text-gray-700 mb-1.5">新密码</span>
          <input v-model="newPassword" type="password" autocomplete="new-password" minlength="10" class="input-field w-full" required />
        </label>
        <label class="block">
          <span class="block text-sm font-medium text-gray-700 mb-1.5">确认新密码</span>
          <input v-model="confirmPassword" type="password" autocomplete="new-password" minlength="10" class="input-field w-full" required />
        </label>
        <p class="text-xs text-gray-500">至少 10 个字符。</p>
        <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
        <button type="submit" class="btn-primary w-full justify-center" :disabled="submitting">
          <Save :size="18" />
          {{ submitting ? '正在保存' : '保存新密码' }}
        </button>
      </form>
    </section>
  </main>
</template>
