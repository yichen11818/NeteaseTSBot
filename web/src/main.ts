import { createApp } from 'vue'
import './style.css'
import { logger } from './utils/logger'
import { loadAppBranding } from './appConfig'
import { initializeTheme } from './theme'
import StartupError from './components/StartupError.vue'
import { currentServerId, loadServerCatalog, serverPageUrl, validateServerSelection, type ServerEntry } from './servers'

// 初始化日志
logger.info('TSBot Web application starting...')
initializeTheme()

async function start(servers: readonly ServerEntry[]): Promise<void> {
  validateServerSelection(servers)
  if (servers.length && !currentServerId()) {
    window.location.replace(serverPageUrl(servers[0].id))
    return
  }
  await loadAppBranding()
  const [{ default: App }, { router }] = await Promise.all([import('./App.vue'), import('./router')])
  const application = createApp(App, { servers }).use(router)
  await router.isReady()
  application.mount('#app')
}

function showStartupError(error: unknown, servers: readonly ServerEntry[]) {
  const message = error instanceof Error ? error.message : String(error)
  logger.error('Control panel startup failed', message)
  createApp(StartupError, { message, servers }).mount('#app')
}

loadServerCatalog().then(
  servers => start(servers).catch(error => showStartupError(error, servers)),
  error => showStartupError(error, []),
)
