const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://127.0.0.1:8000'

export type TokenResponse = { access_token: string }

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('tsbot_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    headers: { ...authHeaders() },
  })
  if (!r.ok) throw new Error(await r.text())
  return (await r.json()) as T
}

export async function apiPost<T>(path: string, body: any): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(await r.text())
  return (await r.json()) as T
}

export async function apiPut<T>(path: string, body: any): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(await r.text())
  return (await r.json()) as T
}

export async function apiDelete<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
  })
  if (!r.ok) throw new Error(await r.text())
  return (await r.json()) as T
}

export function setToken(token: string) {
  localStorage.setItem('tsbot_token', token)
}

export function clearToken() {
  localStorage.removeItem('tsbot_token')
}
