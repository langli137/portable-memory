/**
 * REST 客户端：与原生面板共用同一套后端 API。
 * 令牌存在内存中，不落 localStorage，避免敏感信息持久化。
 */
import type { Memory, Project, ProjectsResponse, Session, Stats } from './types'

let authToken = ''

export function setToken(token: string): void {
  authToken = token.trim()
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  if (authToken) h['Authorization'] = `Bearer ${authToken}`
  return h
}

async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(path, { headers: headers(), ...opts })
  if (res.status === 401) throw new Error('令牌无效')
  const data = await res.json()
  if (!res.ok) throw new Error((data as { error?: string }).error || '请求失败')
  return data as T
}

export const health = () => api<{ ok: boolean; version: string }>('/health')
export const stats = () => api<Stats>('/stats')
export const projects = () => api<ProjectsResponse>('/projects')

export function registerProject(namespace: string, name?: string) {
  return api<Project>('/projects/register', {
    method: 'POST',
    body: JSON.stringify({ namespace, name }),
  })
}

export function listMemories(namespace?: string): Promise<{ items: Memory[] }> {
  const q = namespace ? `?namespace=${encodeURIComponent(namespace)}` : ''
  return api(`/list${q}`)
}

export function recall(query: string, namespace?: string, limit = 50): Promise<{ items: Memory[] }> {
  const parts = [`query=${encodeURIComponent(query)}`, `limit=${limit}`]
  if (namespace) parts.push(`namespace=${encodeURIComponent(namespace)}`)
  return api(`/recall?${parts.join('&')}`)
}

export function remember(payload: {
  content: string
  type?: string
  tags?: string[]
  namespace?: string
  source?: string
}) {
  return api<Memory>('/remember', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateMemory(
  id: number,
  payload: { content: string; type?: string; tags?: string[]; namespace?: string },
) {
  return api<Memory>(`/memory/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteMemory(id: number) {
  return api<{ ok: boolean }>(`/memory/${id}`, { method: 'DELETE' })
}

export function sessions(namespace?: string): Promise<{ items: Session[] }> {
  const q = namespace ? `?namespace=${encodeURIComponent(namespace)}` : ''
  return api(`/sessions${q}`)
}

export function startSession(namespace: string, title: string, tool = 'webui') {
  return api<Session>('/sessions', {
    method: 'POST',
    body: JSON.stringify({ namespace, title, tool }),
  })
}

export function deleteSession(id: number) {
  return api<{ ok: boolean }>(`/sessions/${id}`, { method: 'DELETE' })
}
