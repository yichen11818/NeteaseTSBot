import { getCsrfToken } from './session'
import { DEMO_MODE } from './demoMode'
import { currentServerId } from './servers'

const RAW_API_BASE = (import.meta as any).env?.VITE_API_BASE || '/api'
const DEFAULT_API_BASE = String(RAW_API_BASE).replace(/\/+$/, '')
const RAW_API_TOKEN = (import.meta as any).env?.VITE_API_TOKEN || ''
const API_TOKEN = String(RAW_API_TOKEN).trim()

function apiBase(): string {
  const id = currentServerId()
  return id ? `/api/servers/${id}` : DEFAULT_API_BASE
}

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${apiBase()}${normalized}`
}

function buildHeaders(extraHeaders?: Record<string, string>, contentType?: string): Record<string, string> {
  const headers: Record<string, string> = { ...(extraHeaders || {}) }

  const hasAuthHeader = Object.keys(headers).some((key) => {
    const lower = key.toLowerCase()
    return lower === 'authorization' || lower === 'x-api-token'
  })

  if (API_TOKEN && !hasAuthHeader) {
    headers.Authorization = `Bearer ${API_TOKEN}`
  }

  const hasContentType = Object.keys(headers).some((key) => key.toLowerCase() === 'content-type')
  if (contentType && !hasContentType) {
    headers['Content-Type'] = contentType
  }

  const csrfToken = getCsrfToken()
  if (csrfToken && !Object.keys(headers).some((key) => key.toLowerCase() === 'x-csrf-token')) {
    headers['X-CSRF-Token'] = csrfToken
  }

  return headers
}

async function requestJson<T>(
  path: string,
  init: RequestInit,
): Promise<T> {
  if (DEMO_MODE) {
    const { demoRequest } = await import('./demo/api')
    return demoRequest(path, init) as T
  }
  const r = await fetch(`${apiBase()}${path}`, { ...init, credentials: 'include' })
  if (!r.ok) {
    const text = await r.text()
    let msg = (text || '').trim()
    try {
      const obj = JSON.parse(text)
      if (obj && typeof obj === 'object') {
        const anyObj = obj as any
        const detail = anyObj?.detail
        const message = anyObj?.message
        if (typeof detail === 'string' && detail.trim()) {
          msg = detail.trim()
        } else if (detail?.fields && typeof detail.fields === 'object') {
          msg = Object.entries(detail.fields)
            .map(([field, error]) => `${field}: ${String(error)}`)
            .join('；')
        } else if (typeof message === 'string' && message.trim()) {
          msg = message.trim()
        }
      }
    } catch {
    }
    if (!msg) {
      msg = `HTTP ${r.status}`
    }
    msg = msg.replace(/^\s*\d{3}:\s*/g, '')
    throw new Error(msg)
  }
  return (await r.json()) as T
}

export async function apiGet<T>(path: string, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      headers: buildHeaders(extraHeaders),
    },
  )
}

export async function apiPost<T>(path: string, body: any, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      method: 'POST',
      headers: buildHeaders(extraHeaders, 'application/json'),
      body: JSON.stringify(body),
    },
  )
}

export async function apiPut<T>(path: string, body: any, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      method: 'PUT',
      headers: buildHeaders(extraHeaders, 'application/json'),
      body: JSON.stringify(body),
    },
  )
}

export async function apiDelete<T>(path: string, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      method: 'DELETE',
      headers: buildHeaders(extraHeaders),
    },
  )
}

export async function apiPutFile<T>(path: string, file: File, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      method: 'PUT',
      headers: buildHeaders(extraHeaders, file.type || 'application/octet-stream'),
      body: file,
    },
  )
}
