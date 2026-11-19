<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Check, ChevronDown, Server } from 'lucide-vue-next'
import { serverPageUrl, type ServerEntry } from '../servers'

const props = defineProps<{ servers: readonly ServerEntry[]; selected: string }>()

const open = ref(false)
const activeIndex = ref(0)
const rootRef = ref<HTMLElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const menuId = 'server-selector-menu'

const selectedIndex = computed(() => props.servers.findIndex((server) => server.id === props.selected))
const selectedName = computed(() => props.servers[selectedIndex.value]?.name || '选择服务器')

function setInitialIndex() {
  activeIndex.value = selectedIndex.value >= 0 ? selectedIndex.value : 0
}

async function openMenu() {
  if (!props.servers.length) return
  setInitialIndex()
  open.value = true
  await nextTick()
  menuRef.value?.focus()
}

function closeMenu(restoreFocus = false) {
  open.value = false
  if (restoreFocus) {
    nextTick(() => rootRef.value?.querySelector<HTMLButtonElement>('.server-selector-trigger')?.focus())
  }
}

function toggleMenu() {
  if (open.value) closeMenu()
  else void openMenu()
}

function selectServer(id: string) {
  if (!id) return
  if (id === props.selected) {
    closeMenu(true)
    return
  }
  // A new document releases the previous player's timers and in-flight UI state.
  window.location.assign(serverPageUrl(id))
}

function moveActive(direction: 1 | -1) {
  const count = props.servers.length
  activeIndex.value = (activeIndex.value + direction + count) % count
}

function handleMenuKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeMenu(true)
    return
  }
  if (event.key === 'Tab') {
    closeMenu()
    return
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    moveActive(1)
    return
  }
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    moveActive(-1)
    return
  }
  if (event.key === 'Home') {
    event.preventDefault()
    activeIndex.value = 0
    return
  }
  if (event.key === 'End') {
    event.preventDefault()
    activeIndex.value = props.servers.length - 1
    return
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    selectServer(props.servers[activeIndex.value]?.id || '')
  }
}

function handleTriggerKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    void openMenu()
  }
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (!open.value || !(event.target instanceof Node)) return
  if (!rootRef.value?.contains(event.target)) closeMenu()
}

onMounted(() => document.addEventListener('pointerdown', handleDocumentPointerDown))
onBeforeUnmount(() => document.removeEventListener('pointerdown', handleDocumentPointerDown))
</script>

<template>
  <div v-if="servers.length" ref="rootRef" class="relative min-w-0">
    <button
      type="button"
      class="server-selector-trigger group inline-flex max-w-[12rem] items-center gap-2 rounded-full border bg-white py-1.5 pl-3.5 pr-2.5 text-sm font-medium shadow-sm transition-all duration-200 sm:max-w-[17rem]"
      :class="open
        ? 'border-blue-200 bg-blue-50/60 text-blue-700 shadow'
        : 'border-gray-200 text-gray-600 hover:border-blue-200 hover:text-blue-700 hover:shadow'"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-controls="menuId"
      aria-label="切换 TeamSpeak 服务器"
      @click="toggleMenu"
      @keydown="handleTriggerKeydown"
    >
      <span class="server-selector-icon flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-500 text-white shadow-sm shadow-blue-200">
        <Server :size="13" aria-hidden="true" />
      </span>
      <span class="min-w-0 truncate">{{ selectedName }}</span>
      <ChevronDown
        :size="14"
        class="shrink-0 text-gray-400 transition-transform duration-200"
        :class="{ 'rotate-180 !text-blue-500': open, 'group-hover:text-blue-500': !open }"
        aria-hidden="true"
      />
    </button>

    <Transition name="server-menu-fade">
      <div
        v-if="open"
        ref="menuRef"
        :id="menuId"
        role="listbox"
        tabindex="-1"
        aria-label="TeamSpeak 服务器"
        :aria-activedescendant="`${menuId}-${servers[activeIndex]?.id}`"
        class="server-selector-menu absolute left-0 z-50 mt-2 w-64 max-w-[calc(100vw-2rem)] origin-top-left rounded-2xl border border-gray-100 bg-white/95 p-1.5 shadow-xl shadow-gray-300/30 backdrop-blur-sm outline-none"
        @keydown="handleMenuKeydown"
      >
        <div class="px-3 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-gray-400">
          切换服务器
        </div>
        <button
          v-for="(server, index) in servers"
          :id="`${menuId}-${server.id}`"
          :key="server.id"
          type="button"
          role="option"
          tabindex="-1"
          :aria-selected="server.id === selected"
          class="server-selector-option flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 outline-none"
          :class="[
            server.id === selected ? 'bg-blue-50 text-blue-700' : 'text-gray-600',
            activeIndex === index ? 'server-selector-option-active' : '',
          ]"
          @mouseenter="activeIndex = index"
          @click="selectServer(server.id)"
        >
          <span
            class="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl"
            :class="server.id === selected
              ? 'bg-blue-100 text-blue-600'
              : 'bg-gray-50 text-gray-400'"
          >
            <Server :size="15" aria-hidden="true" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium">{{ server.name }}</span>
            <span class="block text-[11px] text-gray-400">{{ server.id }}</span>
          </span>
          <Check v-if="server.id === selected" :size="16" class="shrink-0 text-blue-500" aria-hidden="true" />
        </button>
      </div>
    </Transition>
  </div>
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

:global(body.theme-dark) .server-selector-trigger {
  border-color: rgb(55 65 81);
  background: rgb(17 24 39);
  color: rgb(209 213 219);
}

:global(body.theme-dark) .server-selector-trigger:hover,
:global(body.theme-dark) .server-selector-trigger[aria-expanded='true'] {
  border-color: rgb(30 64 175);
  background: rgb(23 37 84 / 0.55);
  color: rgb(147 197 253);
}

:global(body.theme-dark) .server-selector-menu {
  border-color: rgb(55 65 81);
  background: rgb(17 24 39 / 0.97);
  box-shadow: 0 20px 45px rgb(0 0 0 / 0.35);
}

:global(body.theme-dark) .server-selector-option {
  color: rgb(209 213 219);
}

:global(body.theme-dark) .server-selector-option:hover,
:global(body.theme-dark) .server-selector-option-active {
  background: rgb(31 41 55);
  color: white;
}

:global(body.theme-dark) .server-selector-option[aria-selected='true'],
:global(body.theme-dark) .server-selector-option[aria-selected='true']:hover {
  background: rgb(30 58 138 / 0.45);
  color: rgb(191 219 254);
}
</style>
