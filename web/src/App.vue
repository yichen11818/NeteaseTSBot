<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import MusicPlayer from './components/MusicPlayer.vue'
import { appConfig } from './appConfig'
import { applyTheme, getInitialTheme } from './theme'
import { DEMO_MODE } from './demoMode'
import { PROJECT_URL, INSTALL_URL } from './projectLinks'
import { 
  Home, 
  Music,
  Search, 
  Heart, 
  ListMusic, 
  Clock, 
  Settings,
  Github,
  Moon,
  Sun,
  Menu,
  X
} from 'lucide-vue-next'

const sidebarOpen = ref(false)
const desktopQuery = window.matchMedia('(min-width: 1024px)')
const isDesktop = ref(desktopQuery.matches)
function syncDesktop(event: MediaQueryListEvent) { isDesktop.value = event.matches }
onMounted(() => desktopQuery.addEventListener('change', syncDesktop))
onBeforeUnmount(() => desktopQuery.removeEventListener('change', syncDesktop))
const appName = computed(() => appConfig.name)
const themeMode = ref<'light' | 'dark'>(getInitialTheme())
const isDarkMode = computed(() => themeMode.value === 'dark')

const route = useRoute()
watch(() => route.fullPath, () => { sidebarOpen.value = false })
const isLyricsRoute = computed(() => route.name === 'lyrics' || route.path.startsWith('/lyrics'))
const isAuthRoute = computed(() => Boolean(route.meta.authPage))

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function toggleTheme() {
  themeMode.value = isDarkMode.value ? 'light' : 'dark'
  applyTheme(themeMode.value)
}
</script>

<template>
  <div :class="['app-shell min-h-screen transition-colors duration-300', isLyricsRoute ? 'bg-black h-[100dvh] overflow-hidden' : 'bg-gray-50']">
    <RouterView v-if="isAuthRoute" />
    <template v-if="isLyricsRoute">
      <div v-if="DEMO_MODE" class="pointer-events-none fixed top-3 right-4 z-50 rounded-full bg-black/50 px-3 py-1 text-xs text-white">在线体验 · 不播放真实音频</div>
      <div class="h-full relative z-0">
        <RouterView v-slot="{ Component, route: currentRoute }">
          <Transition name="route-shell" mode="out-in">
            <div :key="currentRoute.fullPath" class="route-shell-stage h-full min-h-0">
              <component :is="Component" />
            </div>
          </Transition>
        </RouterView>
      </div>
    </template>

    <template v-else-if="!isAuthRoute">
      <!-- Mobile sidebar backdrop -->
      <div 
        v-if="sidebarOpen" 
        class="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
        @click="toggleSidebar"
      ></div>
      
      <!-- Sidebar -->
      <aside 
        :inert="!isDesktop && !sidebarOpen"
        :aria-hidden="!isDesktop && !sidebarOpen"
        :class="[
          'theme-sidebar-shell fixed top-0 left-0 h-full w-64 bg-white/95 backdrop-blur-sm border-r border-gray-200 z-50 transform transition-transform duration-300 ease-out shadow-[4px_0_24px_rgba(0,0,0,0.02)]',
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
              <h1 class="text-lg font-bold text-gray-900 tracking-tight">{{ appName }}</h1>
            </div>
            <button 
              @click="toggleSidebar"
              aria-label="关闭导航"
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
          <div class="theme-sidebar-footer p-4 border-t border-gray-100 bg-gray-50/50">
            <RouterLink 
              to="/settings"
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
      <div class="lg:ml-64 flex flex-col h-[100dvh] pb-24">
        <!-- Top bar -->
        <header class="theme-topbar-shell bg-white border-b border-gray-200 px-4 md:px-6 py-3 md:py-4 flex-shrink-0 flex items-center justify-between">
          <div class="flex items-center gap-4">
            <button 
              @click="toggleSidebar"
              aria-label="打开导航"
              class="lg:hidden p-2 text-gray-500 hover:text-gray-700 -ml-2"
            >
              <Menu :size="20" />
            </button>
          </div>
          
          <div class="flex items-center gap-2">
            <a
              :href="PROJECT_URL"
              target="_blank"
              rel="noreferrer"
              class="theme-toolbar-btn p-2 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
              title="项目仓库 / Star"
              aria-label="项目仓库 / Star"
            >
              <Github :size="20" />
            </a>
            <button
              type="button"
              :class="[
                'theme-toolbar-btn p-2 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors',
                isDarkMode ? 'theme-toolbar-btn-active' : ''
              ]"
              :title="isDarkMode ? '切换到浅色模式' : '切换到夜间模式'"
              @click="toggleTheme"
            >
              <Moon v-if="!isDarkMode" :size="20" />
              <Sun v-else :size="20" />
            </button>
            <RouterLink
              to="/settings"
              class="theme-toolbar-btn p-2 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
              title="设置"
            >
              <Settings :size="20" />
            </RouterLink>
          </div>
        </header>

        <div v-if="DEMO_MODE" role="note" class="demo-banner flex flex-wrap items-center justify-between gap-2 border-b border-blue-200 bg-blue-50 px-4 py-2 text-xs text-blue-900 md:px-6">
          <span><strong>在线体验</strong> · 模拟数据，不播放真实音频；刷新即可重置队列和设置。</span>
          <a :href="INSTALL_URL" target="_blank" rel="noopener noreferrer" class="font-semibold underline underline-offset-2">部署到自己的频道 ↗</a>
        </div>
        
        <!-- Content area -->
        <main class="flex-1 min-h-0 relative z-0">
          <RouterView v-slot="{ Component, route: currentRoute }">
            <Transition name="route-shell" mode="out-in">
              <div :key="currentRoute.fullPath" class="route-shell-stage h-full min-h-0">
                <component :is="Component" />
              </div>
            </Transition>
          </RouterView>
        </main>
      </div>
    </template>
    
    <!-- Music Player -->
    <MusicPlayer v-if="!isLyricsRoute && !isAuthRoute" />
  </div>
</template>
