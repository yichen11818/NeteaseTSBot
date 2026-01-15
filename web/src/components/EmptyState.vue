<script setup lang="ts">
import { type Component } from 'vue'

defineProps<{
  icon?: Component
  title?: string
  description?: string
  actionText?: string
}>()

defineEmits<{
  (e: 'action'): void
}>()
</script>

<template>
  <div class="flex flex-col items-center justify-center py-12 text-center fade-in">
    <div v-if="icon" class="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4 text-gray-400">
      <component :is="icon" :size="32" />
    </div>
    
    <h3 v-if="title" class="text-lg font-medium text-gray-900 mb-1">
      {{ title }}
    </h3>
    
    <p v-if="description" class="text-gray-500 max-w-sm mx-auto mb-6">
      {{ description }}
    </p>

    <slot />
    
    <button 
      v-if="actionText"
      @click="$emit('action')"
      class="btn-primary"
    >
      {{ actionText }}
    </button>
  </div>
</template>
