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
const isLyricsRoute = computed(() => route.name === 'lyrics' || route.path.startsWith('/lyrics'))

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}
</script>

<template>
  <div :class="['min-h-screen transition-colors duration-300', isLyricsRoute ? 'bg-black h-[100dvh] overflow-hidden' : 'bg-gray-50 pb-24']">
    <template v-if="isLyricsRoute">
      <div class="h-full relative z-0">
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
          'fixed top-0 left-0 h-full w-64 bg-white/95 backdrop-blur-sm border-r border-gray-200 z-50 transform transition-transform duration-300 ease-out shadow-[4px_0_24px_rgba(0,0,0,0.02)]',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        ]"
      >
        <div class="flex flex-col h-full">
          <!-- Logo/Brand -->
          <div class="flex items-center justify-between px-6 py-5 border-b border-gray-100">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 bg-gradient-to-tr from-blue-600 to-indigo-500 rounded-lg flex items-center justify-center text-white shadow-md shadow-blue-200">
                <Music :size="18" fill="currentColor" />
              </div>
              <h1 class="text-lg font-bold text-gray-900 tracking-tight">TSBot Music</h1>
            </div>
            <button 
              @click="toggleSidebar"
              class="lg:hidden p-2 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X :size="20" />
            </button>
          </div>
          
          <!-- Navigation -->
          <nav class="flex-1 px-4 py-6 overflow-y-auto scrollbar-thin">
            <div class="space-y-1.5">
              <div class="px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 mt-1">发现</div>
              
              <RouterLink 
                to="/search" 
                class="nav-item"
                active-class="nav-item-active"
              >
                <Search :size="20" />
                <span>搜索</span>
              </RouterLink>
              
              <RouterLink 
                to="/playlists" 
                class="nav-item"
                active-class="nav-item-active"
              >
                <ListMusic :size="20" />
                <span>歌单广场</span>
              </RouterLink>
            </div>
            
            <div class="space-y-1.5 mt-8">
              <div class="px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">我的音乐</div>
              
              <RouterLink 
                to="/queue" 
                class="nav-item"
                active-class="nav-item-active"
              >
                <ListMusic :size="20" />
                <span>播放队列</span>
              </RouterLink>
              
              <RouterLink 
                to="/likes" 
                class="nav-item"
                active-class="nav-item-active"
              >
                <Heart :size="20" />
                <span>我喜欢的</span>
              </RouterLink>

              <RouterLink 
                to="/favorites" 
                class="nav-item"
                active-class="nav-item-active"
              >
                <Heart :size="20" />
                <span>本地收藏</span>
              </RouterLink>
              
              <RouterLink 
                to="/history" 
                class="nav-item"
                active-class="nav-item-active"
              >
                <Clock :size="20" />
                <span>最近播放</span>
              </RouterLink>
            </div>
          </nav>
          
          <!-- User/Settings Footer -->
          <div class="p-4 border-t border-gray-100 bg-gray-50/50">
            <RouterLink 
              to="/cookie" 
              class="nav-item"
              active-class="nav-item-active"
            >
              <Settings :size="20" />
              <span>设置</span>
            </RouterLink>
          </div>
        </div>
      </aside>
      
      <!-- Main content -->
      <div class="lg:ml-64 flex flex-col h-[100dvh]">
        <!-- Top bar -->
        <header class="bg-white border-b border-gray-200 px-4 md:px-6 py-3 md:py-4 flex-shrink-0 flex items-center justify-between">
          <div class="flex items-center gap-4">
            <button 
              @click="toggleSidebar"
              class="lg:hidden p-2 text-gray-500 hover:text-gray-700 -ml-2"
            >
              <Menu :size="20" />
            </button>
          </div>
          
          <div class="flex items-center gap-2">
            <RouterLink
              to="/cookie"
              class="p-2 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
              title="设置"
            >
              <Settings :size="20" />
            </RouterLink>
          </div>
        </header>
        
        <!-- Content area -->
        <main class="flex-1 min-h-0 relative z-0">
          <RouterView />
        </main>
      </div>
    </template>
    
    <!-- Music Player -->
    <MusicPlayer v-if="!isLyricsRoute" />
  </div>
</template>
