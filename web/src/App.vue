<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import MusicPlayer from './components/MusicPlayer.vue'
import { 
  Home, 
  Search, 
  Heart, 
  ListMusic, 
  Clock, 
  Settings,
  Menu,
  X
} from 'lucide-vue-next'

const sidebarOpen = ref(false)

const route = useRoute()
const isLyricsRoute = computed(() => route.path === '/lyrics')

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-24">
    <template v-if="isLyricsRoute">
      <div class="h-[calc(100vh-96px)]">
        <RouterView />
      </div>
    </template>

    <template v-else>
      <!-- Mobile sidebar backdrop -->
      <div 
        v-if="sidebarOpen" 
        class="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
        @click="toggleSidebar"
      ></div>
      
      <!-- Sidebar -->
      <aside 
        :class="[
          'fixed top-0 left-0 h-full w-64 bg-white border-r border-gray-200 z-50 transform transition-transform duration-300 ease-in-out',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        ]"
      >
        <div class="flex flex-col h-full">
          <!-- Logo/Brand -->
          <div class="flex items-center justify-between p-6 border-b border-gray-200">
            <h1 class="text-xl font-bold text-gray-900">TSBot Music</h1>
            <button 
              @click="toggleSidebar"
              class="lg:hidden p-2 text-gray-500 hover:text-gray-700"
            >
              <X :size="20" />
            </button>
          </div>
          
          <!-- Navigation -->
          <nav class="flex-1 p-4">
            <div class="space-y-2">
              <RouterLink 
                to="/search" 
                class="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors"
                active-class="bg-blue-50 text-blue-700"
              >
                <Search :size="20" />
                <span>搜索</span>
              </RouterLink>
              
              <RouterLink 
                to="/queue" 
                class="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors"
                active-class="bg-blue-50 text-blue-700"
              >
                <ListMusic :size="20" />
                <span>播放队列</span>
              </RouterLink>
              
              <RouterLink 
                to="/likes" 
                class="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors"
                active-class="bg-blue-50 text-blue-700"
              >
                <Heart :size="20" />
                <span>我的喜欢</span>
              </RouterLink>
              
              <RouterLink 
                to="/playlists" 
                class="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors"
                active-class="bg-blue-50 text-blue-700"
              >
                <ListMusic :size="20" />
                <span>我的歌单</span>
              </RouterLink>
              
              <RouterLink 
                to="/history" 
                class="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors"
                active-class="bg-blue-50 text-blue-700"
              >
                <Clock :size="20" />
                <span>播放历史</span>
              </RouterLink>
            </div>
            
            <div class="mt-8 pt-4 border-t border-gray-200">
              <RouterLink 
                to="/cookie" 
                class="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors"
                active-class="bg-blue-50 text-blue-700"
              >
                <Settings :size="20" />
                <span>设置</span>
              </RouterLink>
            </div>
          </nav>
        </div>
      </aside>
      
      <!-- Main content -->
      <div class="lg:ml-64">
        <!-- Top bar -->
        <header class="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <div class="flex items-center gap-4">
            <button 
              @click="toggleSidebar"
              class="lg:hidden p-2 text-gray-500 hover:text-gray-700"
            >
              <Menu :size="20" />
            </button>
          </div>
          
          <div class="flex items-center gap-4"></div>
        </header>
        
        <!-- Content area -->
        <main class="flex h-[calc(100vh-73px-96px)]">
          <!-- Main content -->
          <div class="flex-1 min-h-0 overflow-y-auto">
            <RouterView />
          </div>
        </main>
      </div>
    </template>
    
    <!-- Music Player -->
    <MusicPlayer />
  </div>
</template>
