const STORAGE_KEY = 'sentinel_backend_url'
const DEFAULT_URL = 'http://localhost:8000'

export function getBackendUrl(): string {
  return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_URL
}

export function setBackendUrl(url: string): void {
  const clean = url.replace(/\/+$/, '')
  localStorage.setItem(STORAGE_KEY, clean)
}

export function clearBackendUrl(): void {
  localStorage.removeItem(STORAGE_KEY)
}

function BASE() {
  return getBackendUrl() + '/api'
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE() + path, {
    headers: {
      'Content-Type': 'application/json',
      'ngrok-skip-browser-warning': 'true',
      ...init?.headers,
    },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const api = {
  status:      () => req<SystemStatus>('/status'),
  runs:        (limit = 50, repo?: string) =>
                 req<{ runs: Run[]; total: number }>(`/runs?limit=${limit}${repo ? `&repo=${repo}` : ''}`),
  run:         (id: string) => req<Run>(`/runs/${id}`),
  kbStats:     () => req<KBStats>('/kb/stats'),
  approvals:   (status = 'pending') => req<{ approvals: Approval[]; total: number }>(`/approvals?status=${status}`),
  approve:     (id: string, reviewer = 'human') =>
                 req(`/approvals/${id}/approve`, { method: 'POST', body: JSON.stringify({ reviewer }) }),
  reject:      (id: string, reviewer = 'human') =>
                 req(`/approvals/${id}/reject`, { method: 'POST', body: JSON.stringify({ reviewer }) }),
  agentStatus: () => req<AgentStatusResponse>('/agents/status'),
  triggerMaintenance: (agent = 'all', repo_root = '.') =>
                 req('/maintenance/trigger', { method: 'POST', body: JSON.stringify({ agent, repo_root }) }),
  triggerPipeline: (repo: string, pr_number: number) =>
                 req('/pipeline/trigger', { method: 'POST', body: JSON.stringify({ repo, pr_number }) }),
  patterns:    () => req<{ patterns: Pattern[]; total: number }>('/patterns'),
}

// ── Types ──────────────────────────────────────────────────────────────────────

export interface SystemStatus {
  status: 'healthy' | 'degraded'
  version: string
  kb: { ok: boolean; entries: number }
  last_run: { status: string | null; ran_at: string | null }
  llm_provider: string
  timestamp: string
}

export interface Run {
  run_id?: string
  repo: string
  pr: number
  started_at: string
  completed_at?: string
  status: string
  findings?: number
  regressions?: number
  finding_categories?: Record<string, number>
  tests_generated?: number
  bugs_found?: number
  auto_fixes?: number
  pending_fixes?: number
  risk_level?: string
  risk_score?: number
  token_total?: number
  est_cost_usd?: number
  error?: string
}

export interface Pattern {
  type: string
  title: string
  description: string
  severity: 'high' | 'medium' | 'low'
  evidence: Record<string, unknown>
  detected_at: string
}

export interface KBStats {
  total: number
  active: number
  archived: number
  invalidated: number
  superseded: number
  by_type: Record<string, number>
  confidence: { average: number; high: number; medium: number; low: number }
  top_used: Array<{ id: string; title: string; type: string; use_count: number; confidence: number }>
}

export interface Approval {
  id: string
  repo: string
  pr: number
  description: string
  rationale: string
  patch: string
  affected_files: string[]
  classification: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
  reviewed_at?: string
  reviewed_by?: string
  run_id?: string
}

export interface AgentInfo {
  name: string
  id: string
  role: string
  schedule: string
  swarm: string
  last_run?: string
  last_result?: Record<string, unknown>
}

export interface AgentStatusResponse {
  agents: AgentInfo[]
  recent_maintenance: Array<Record<string, unknown>>
}
