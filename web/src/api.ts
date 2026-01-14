const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://127.0.0.1:8009'

async function requestJson<T>(
  path: string,
  init: RequestInit,
): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, init)
  if (!r.ok) {
    const text = await r.text()
    throw new Error(text)
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
