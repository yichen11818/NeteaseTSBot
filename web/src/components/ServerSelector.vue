<script setup lang="ts">
import { computed } from 'vue'
import { Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/vue'
import { Check, ChevronDown, Server } from 'lucide-vue-next'
import { serverPageUrl, type ServerEntry } from '../servers'

const props = defineProps<{ servers: readonly ServerEntry[]; selected: string }>()
const selectedName = computed(() => props.servers.find(server => server.id === props.selected)?.name || '选择服务器')

function selectServer(id: string) {
  if (id === props.selected) return
  // Reload the document to release the previous player's timers and UI state.
  window.location.assign(serverPageUrl(id))
}
</script>

<template>
  <Listbox v-if="servers.length" v-slot="{ open }" as="div" class="relative min-w-0"
    :model-value="selected" @update:model-value="selectServer">
    <ListboxButton
      class="server-selector-trigger group inline-flex max-w-[40vw] items-center gap-2 rounded-full border bg-white py-1.5 pl-3.5 pr-2.5 text-sm font-medium shadow-sm transition-all duration-200 sm:max-w-[17rem]"
      :class="open ? 'border-blue-200 bg-blue-50/60 text-blue-700 shadow' : 'border-gray-200 text-gray-600 hover:border-blue-200 hover:text-blue-700 hover:shadow'"
      aria-label="切换 TeamSpeak 服务器">
      <span class="server-selector-icon flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-500 text-white shadow-sm shadow-blue-200">
        <Server :size="13" aria-hidden="true" />
      </span>
      <span class="min-w-0 truncate">{{ selectedName }}</span>
      <ChevronDown :size="14" class="shrink-0 text-gray-400 transition-transform duration-200"
        :class="{ 'rotate-180 !text-blue-500': open, 'group-hover:text-blue-500': !open }" aria-hidden="true" />
    </ListboxButton>
    <Transition name="server-menu-fade">
      <ListboxOptions aria-label="TeamSpeak 服务器"
        class="server-selector-menu absolute left-0 z-50 mt-2 max-h-[60dvh] w-64 max-w-[calc(100vw-5rem)] overflow-y-auto origin-top-left rounded-2xl border border-gray-100 bg-white/95 p-1.5 shadow-xl shadow-gray-300/30 backdrop-blur-sm outline-none">
        <ListboxOption v-for="server in servers" :key="server.id" v-slot="{ active, selected: isSelected }"
          :value="server.id" as="template">
          <li class="server-selector-option flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 outline-none"
            :class="[isSelected ? 'bg-blue-50 text-blue-700' : 'text-gray-600', active ? 'server-selector-option-active' : '']">
            <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl"
              :class="isSelected ? 'bg-blue-100 text-blue-600' : 'bg-gray-50 text-gray-400'">
              <Server :size="15" aria-hidden="true" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-medium">{{ server.name }}</span>
              <span class="block text-[11px] text-gray-400">{{ server.id }}</span>
            </span>
            <Check v-if="isSelected" :size="16" class="shrink-0 text-blue-500" aria-hidden="true" />
          </li>
        </ListboxOption>
      </ListboxOptions>
    </Transition>
  </Listbox>
</template>

<style scoped>
.server-menu-fade-enter-active,
.server-menu-fade-leave-active {
  transition: opacity 160ms ease, transform 160ms ease;
}

.server-menu-fade-enter-from,
.server-menu-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}

.server-selector-option:hover,
.server-selector-option-active {
  background: rgb(249 250 251);
  color: rgb(17 24 39);
}

.server-selector-option[aria-selected='true'],
.server-selector-option[aria-selected='true']:hover {
  background: rgb(239 246 255);
  color: rgb(29 78 216);
}

:global(body.theme-dark .server-selector-trigger) {
  border-color: rgb(55 65 81);
  background: rgb(17 24 39);
  color: rgb(209 213 219);
}

:global(body.theme-dark .server-selector-trigger:hover),
:global(body.theme-dark .server-selector-trigger[aria-expanded='true']) {
  border-color: rgb(30 64 175);
  background: rgb(23 37 84 / 0.55);
  color: rgb(147 197 253);
}

:global(body.theme-dark .server-selector-menu) {
  border-color: rgb(55 65 81);
  background: rgb(17 24 39 / 0.97);
  box-shadow: 0 20px 45px rgb(0 0 0 / 0.35);
}

:global(body.theme-dark .server-selector-option) {
  color: rgb(209 213 219);
}

:global(body.theme-dark .server-selector-option:hover),
:global(body.theme-dark .server-selector-option-active) {
  background: rgb(31 41 55);
  color: white;
}

:global(body.theme-dark .server-selector-option[aria-selected='true']),
:global(body.theme-dark .server-selector-option[aria-selected='true']:hover) {
  background: rgb(30 58 138 / 0.45);
  color: rgb(191 219 254);
}
</style>
