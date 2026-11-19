<script setup lang="ts">
import { computed } from 'vue'
import { Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/vue'
import { ArrowUpDown, Check, ChevronDown } from 'lucide-vue-next'
import type { LikesSortMode } from '../composables/useLikesDisplay'

const props = defineProps<{ modelValue: LikesSortMode }>()
const emit = defineEmits<{ 'update:modelValue': [value: LikesSortMode] }>()
const options: readonly { value: LikesSortMode; label: string }[] = [
  { value: 'default', label: '顺序' },
  { value: 'added', label: '添加时间（新→旧）' },
  { value: 'name', label: '名称（A→Z）' },
]
const label = computed(() => options.find(option => option.value === props.modelValue)?.label)
</script>

<template>
  <Listbox v-slot="{ open }" as="div" class="relative" :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)">
    <ListboxButton aria-label="排序方式" title="排序方式"
      class="likes-sort-trigger inline-flex max-w-[38vw] items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 shadow-sm hover:text-red-600"
      :class="{ 'border-red-200 text-red-600': open }">
      <ArrowUpDown :size="15" class="shrink-0" aria-hidden="true" />
      <span class="truncate">{{ label }}</span>
      <ChevronDown :size="14" class="shrink-0 transition-transform" :class="{ 'rotate-180': open }" aria-hidden="true" />
    </ListboxButton>
    <ListboxOptions aria-label="排序方式"
      class="likes-sort-menu absolute right-0 z-30 mt-2 w-52 rounded-2xl border border-gray-100 bg-white p-1.5 shadow-xl outline-none">
      <ListboxOption v-for="option in options" :key="option.value" v-slot="{ active, selected }"
        as="template" :value="option.value">
        <li class="likes-sort-option flex cursor-pointer items-center justify-between rounded-xl px-3 py-2 text-sm"
          :class="{ 'bg-red-50 text-red-600': selected, 'bg-gray-100': active }">
          <span>{{ option.label }}</span>
          <Check v-if="selected" :size="15" aria-hidden="true" />
        </li>
      </ListboxOption>
    </ListboxOptions>
  </Listbox>
</template>

<style scoped>
:global(body.theme-dark .likes-sort-trigger),
:global(body.theme-dark .likes-sort-menu) {
  border-color: rgb(55 65 81);
  background: rgb(17 24 39);
  color: rgb(209 213 219);
}
:global(body.theme-dark .likes-sort-option[data-headlessui-state~='active']) {
  background: rgb(55 65 81);
}
:global(body.theme-dark .likes-sort-option[aria-selected='true']) {
  color: rgb(252 165 165);
  background: rgb(127 29 29 / 0.4);
}
</style>
