<script setup lang="ts">
import { Loader2 } from 'lucide-vue-next'

withDefaults(defineProps<{
  size?: number
  text?: string
  fullScreen?: boolean
}>(), {
  size: 32,
  text: 'Loading...',
  fullScreen: false
})
</script>

<template>
  <div 
    class="flex flex-col items-center justify-center p-4"
    :class="{ 'fixed inset-0 bg-white/80 z-50': fullScreen }"
  >
    <Loader2 
      class="animate-spin text-blue-600 mb-3" 
      :size="size"
    />
    <div v-if="text" class="text-gray-500 text-sm font-medium">
      {{ text }}
    </div>
  </div>
</template>
