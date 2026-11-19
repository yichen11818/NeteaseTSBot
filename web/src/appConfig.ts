import { logger } from './utils/logger'
import { reactive } from 'vue'
import { apiGet, apiUrl } from './api'

const rawEnv = (import.meta as any).env || {}

function readString(name: string, fallback: string = ''): string {
  const value = rawEnv?.[name]
  if (typeof value !== 'string') return fallback
  const trimmed = value.trim()
  return trimmed || fallback
}

export const appConfig = reactive({
  name: readString('VITE_WEB_APP_NAME', 'TSBot Music'),
  iconHref: readString('VITE_WEB_APP_ICON', ''),
  publicUrl: readString('VITE_WEB_PUBLIC_URL', ''),
  logLevel: readString('VITE_LOG_LEVEL', 'INFO'),
})

export async function loadAppBranding(): Promise<void> {
  try {
    const config = await apiGet<any>('/config/public')
    if (typeof config?.app_name === 'string' && config.app_name) appConfig.name = config.app_name
    if (typeof config?.app_icon === 'string') {
      appConfig.iconHref = config.app_icon.startsWith('/assets/')
        ? apiUrl(config.app_icon)
        : config.app_icon
    }
    if (typeof config?.log_level === 'string' && config.log_level) appConfig.logLevel = config.log_level
  } catch {
  }
  logger.setLevelName(appConfig.logLevel)
  applyAppBranding()
}

function ensureMeta(selector: string, create: () => HTMLElement): HTMLElement {
  const existing = document.head.querySelector(selector)
  if (existing instanceof HTMLElement) {
    return existing
  }
  const node = create()
  document.head.appendChild(node)
  return node
}

export function applyAppBranding(): void {
  document.title = appConfig.name

  const applicationName = ensureMeta('meta[name="application-name"]', () => {
    const meta = document.createElement('meta')
    meta.setAttribute('name', 'application-name')
    return meta
  })
  applicationName.setAttribute('content', appConfig.name)

  const ogSiteName = ensureMeta('meta[property="og:site_name"]', () => {
    const meta = document.createElement('meta')
    meta.setAttribute('property', 'og:site_name')
    return meta
  })
  ogSiteName.setAttribute('content', appConfig.name)

  const ogTitle = ensureMeta('meta[property="og:title"]', () => {
    const meta = document.createElement('meta')
    meta.setAttribute('property', 'og:title')
    return meta
  })
  ogTitle.setAttribute('content', appConfig.name)

  if (appConfig.iconHref) {
    const iconLink = ensureMeta('link[rel="icon"]', () => {
      const link = document.createElement('link')
      link.setAttribute('rel', 'icon')
      return link
    })
    iconLink.setAttribute('href', appConfig.iconHref)

    const shortcutIcon = ensureMeta('link[rel="shortcut icon"]', () => {
      const link = document.createElement('link')
      link.setAttribute('rel', 'shortcut icon')
      return link
    })
    shortcutIcon.setAttribute('href', appConfig.iconHref)
  } else {
    document.head.querySelectorAll('link[rel="icon"], link[rel="shortcut icon"]').forEach((node) => node.remove())
  }

  if (appConfig.publicUrl) {
    const canonical = ensureMeta('link[rel="canonical"]', () => {
      const link = document.createElement('link')
      link.setAttribute('rel', 'canonical')
      return link
    })
    canonical.setAttribute('href', appConfig.publicUrl)

    const ogUrl = ensureMeta('meta[property="og:url"]', () => {
      const meta = document.createElement('meta')
      meta.setAttribute('property', 'og:url')
      return meta
    })
    ogUrl.setAttribute('content', appConfig.publicUrl)
  }
}
