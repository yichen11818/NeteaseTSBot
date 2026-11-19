<script setup lang="ts">
import ServerSelector from './ServerSelector.vue'
import type { ServerEntry } from '../servers'

defineProps<{ message: string; servers: readonly ServerEntry[] }>()
const reload = () => window.location.reload()
</script>

<template>
  <main class="flex min-h-screen items-center justify-center bg-gray-50 p-6">
    <section class="w-full max-w-lg space-y-5 rounded-xl border border-red-200 bg-white p-6 shadow-sm">
      <h1 class="text-xl font-semibold text-gray-900">暂时无法打开控制台</h1>
      <p role="alert" class="break-words text-sm text-red-700">{{ message }}</p>
      <p class="text-sm text-gray-600">可以重新加载，或切换到其他服务器。当前服务器的播放不会因此停止。</p>
      <ServerSelector :servers="servers" selected="" />
      <button type="button" class="btn-primary" @click="reload">重新加载</button>
    </section>
  </main>
</template>
