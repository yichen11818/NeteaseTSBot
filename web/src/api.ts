const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://127.0.0.1:8009'

async function requestJson<T>(
  path: string,
  init: RequestInit,
): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, init)
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
        } else if (typeof message === 'string' && message.trim()) {
          msg = message.trim()
        }
      }
    } catch {
      // ignore
    }
    if (!msg) {
      msg = `HTTP ${r.status}`
    }
    // Some backends/proxies may prefix messages like "503: <detail>".
    // Normalize to the human message for UI.
    msg = msg.replace(/^\s*\d{3}:\s*/g, '')
    throw new Error(msg)
  }
  return (await r.json()) as T
}

export async function apiGet<T>(path: string, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      headers: { ...(extraHeaders || {}) },
    },
  )
}

export async function apiPost<T>(path: string, body: any, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(extraHeaders || {}) },
      body: JSON.stringify(body),
    },
  )
}

export async function apiPut<T>(path: string, body: any, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...(extraHeaders || {}) },
      body: JSON.stringify(body),
    },
  )
}

export async function apiDelete<T>(path: string, extraHeaders?: Record<string, string>): Promise<T> {
  return await requestJson<T>(
    path,
    {
      method: 'DELETE',
      headers: { ...(extraHeaders || {}) },
    },
  )
}
