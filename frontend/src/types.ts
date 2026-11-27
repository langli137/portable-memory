/** API 契约类型，与 Python 服务端的 to_dict() 对齐。 */

export interface Memory {
  id: number
  content: string
  memory_type: string
  type?: string
  tags: string[]
  namespace: string
  source: string | null
  importance: number
  access_count: number
  created_at: number
  updated_at: number
  score?: number
  bm25?: number
  recency?: number
  frequency?: number
  matched_terms?: string[]
}

export interface Project {
  namespace: string
  name: string
  created_at: number
  last_active: number
}

export interface Session {
  id: number
  project: string
  title: string | null
  tool: string | null
  started_at: number
  ended_at: number | null
  summary: string | null
  memory_count: number
}

export interface Stats {
  total: number
  namespaces: number
  total_accesses: number
}

export interface ProjectsResponse {
  count: number
  items: Project[]
  active_namespace: string | null
}
