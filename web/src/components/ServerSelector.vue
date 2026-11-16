<script setup lang="ts">
import { Server } from 'lucide-vue-next'
import { serverPageUrl, type ServerEntry } from '../servers'

defineProps<{ servers: readonly ServerEntry[]; selected: string }>()

function selectServer(event: Event) {
  const id = (event.target as HTMLSelectElement).value
  // A new document releases the previous player's timers and in-flight UI state.
  window.location.assign(serverPageUrl(id))
}
</script>

<template>
  <label v-if="servers.length" class="flex min-w-0 items-center gap-2 text-sm text-gray-600">
    <Server :size="18" class="shrink-0" aria-hidden="true" />
    <span class="sr-only">当前服务器</span>
    <select
      :value="selected"
      aria-label="当前服务器"
      class="input-field min-w-0 max-w-[180px] py-1.5 text-sm sm:max-w-[260px]"
      @change="selectServer"
    >
      <option v-if="!servers.some(server => server.id === selected)" value="" disabled>选择服务器</option>
      <option v-for="server in servers" :key="server.id" :value="server.id">{{ server.name }}</option>
    </select>
  </label>
</template>
