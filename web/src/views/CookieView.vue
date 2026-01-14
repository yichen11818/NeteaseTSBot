<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiGet, apiPost } from '../api'

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

<template>
  <h2>Netease QR Login</h2>

  <h3>User</h3>
  <p>Used to fetch your likes/playlists. Cookie is stored in localStorage.</p>
  <div style="display:flex; gap:8px; align-items:center; flex-wrap: wrap;">
    <button @click="startUserQr">Start user QR login</button>
    <button @click="clearUserCookie">Clear user cookie</button>
    <button @click="load">Reload</button>
    <span style="opacity:0.7;">logged in: {{ userCookie ? 'yes' : 'no' }}</span>
  </div>
  <div v-if="userQrImg" style="margin-top: 10px;">
    <img :src="userQrImg" alt="user qr" />
  </div>

  <div style="margin-top: 18px;">
    <h3>Admin</h3>
    <p>Used for playback. Cookie is stored encrypted on the server and never returned to the browser.</p>
    <div style="display:flex; gap:8px; align-items:center; flex-wrap: wrap;">
      <button @click="startAdminQr">Start admin QR login</button>
      <button @click="load">Refresh status</button>
      <span style="opacity:0.7;">admin cookie set: {{ adminStatus ? 'yes' : 'no' }}</span>
    </div>

    <div style="margin-top: 10px; display:flex; gap:8px; align-items:center; flex-wrap: wrap;">
      <input v-model="adminManualCookie" placeholder="admin cookie (will be encrypted on server)" style="min-width: 360px;" />
      <input v-model="adminToken" placeholder="admin token (optional)" style="min-width: 220px;" />
      <button @click="setAdminCookie">Save admin cookie</button>
    </div>

    <div v-if="adminQrImg" style="margin-top: 10px;">
      <img :src="adminQrImg" alt="admin qr" />
    </div>
  </div>

  <pre v-if="status" style="white-space:pre-wrap;">{{ status }}</pre>
</template>
