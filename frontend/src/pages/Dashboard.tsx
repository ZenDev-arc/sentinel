import { useState, useRef, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from 'recharts'
import {
  Activity, Database, CheckCircle2, XCircle, Clock, RefreshCw,
  Play, AlertTriangle, ChevronRight, Loader2, ExternalLink, RotateCcw,
  TrendingUp, Zap,
} from 'lucide-react'
import clsx from 'clsx'
import { useApi } from '../hooks/useApi'
import { api, getBackendUrl, setBackendUrl, clearBackendUrl, type KBStats, type Run, type Approval, type AgentInfo, type Pattern } from '../api/client'

// ── Shared ────────────────────────────────────────────────────────────────────

function StatCard({
  label, value, sub, color = 'text-text-primary', icon: Icon,
}: {
  label: string; value: string | number; sub?: string; color?: string; icon: typeof Activity
}) {
  return (
    <div className="card flex items-start gap-4">
      <div className="w-9 h-9 rounded-lg bg-bg-raised border border-bg-border flex items-center justify-center shrink-0">
        <Icon className="w-4 h-4 text-text-muted" />
      </div>
      <div>
        <div className={`text-2xl font-bold ${color}`}>{value}</div>
        <div className="text-xs text-text-muted mt-0.5">{label}</div>
        {sub && <div className="text-xs text-text-muted mt-0.5">{sub}</div>}
      </div>
    </div>
  )
}

function Spinner() {
  return <Loader2 className="w-5 h-5 text-text-muted animate-spin mx-auto" />
}

function EmptyState({ msg }: { msg: string }) {
  return (
    <div className="py-10 text-center text-sm text-text-muted">{msg}</div>
  )
}

const riskColor: Record<string, string> = {
  low:    'text-white',
  medium: 'text-amber-400',
  high:   'text-red-400',
}
const riskBg: Record<string, string> = {
  low:    'bg-white/5 border-white/20',
  medium: 'bg-amber-500/10 border-amber-500/30',
  high:   'bg-red-500/10 border-red-500/30',
}
const statusIcon: Record<string, JSX.Element> = {
  done:    <CheckCircle2 className="w-4 h-4 text-orange-400" />,
  failed:  <XCircle className="w-4 h-4 text-red-400" />,
  running: <Loader2 className="w-4 h-4 text-orange-400 animate-spin" />,
}

// ── Sections ──────────────────────────────────────────────────────────────────

function KBHealthSection() {
  const { data, loading, error, refetch } = useApi(() => api.kbStats(), [], { interval: 30_000 })

  if (loading) return <div className="card"><Spinner /></div>
  if (error || !data) return (
    <div className="card text-sm text-red-400 flex items-center gap-2">
      <AlertTriangle className="w-4 h-4" /> {error ?? 'Failed to load KB stats'}
    </div>
  )

  const byType = Object.entries(data.by_type).map(([name, value]) => ({ name, value }))
  const confDist = [
    { name: 'High (≥0.7)',    value: data.confidence.high,   fill: '#34d399' },
    { name: 'Medium (0.4–0.7)', value: data.confidence.medium, fill: '#fbbf24' },
    { name: 'Low (<0.4)',     value: data.confidence.low,    fill: '#f87171' },
  ]

  return (
    <div className="space-y-4">
      {/* Stat row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Total entries',  v: data.total,       color: 'text-text-primary' },
          { label: 'Active',         v: data.active,      color: 'text-orange-400' },
          { label: 'Archived',       v: data.archived,    color: 'text-text-muted' },
          { label: 'Avg confidence', v: (data.confidence.average * 100).toFixed(0) + '%', color: 'text-orange-400' },
        ].map(({ label, v, color }) => (
          <div key={label} className="card text-center">
            <div className={`text-xl font-bold ${color}`}>{v}</div>
            <div className="text-xs text-text-muted mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* By type bar */}
        <div className="card">
          <p className="text-xs text-text-muted mb-4 uppercase tracking-wider">Entries by type</p>
          {byType.length === 0
            ? <EmptyState msg="No KB entries yet" />
            : (
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={byType} margin={{ left: -20 }}>
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#55557a' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#55557a' }} />
                  <Tooltip
                    contentStyle={{ background: '#12121f', border: '1px solid #1e1e35', borderRadius: 8, fontSize: 12 }}
                    cursor={{ fill: '#1e1e35' }}
                  />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {byType.map((_, i) => (
                      <Cell key={i} fill={['#8b5cf6', '#22d3ee', '#34d399', '#fbbf24'][i % 4]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
        </div>

        {/* Confidence distribution */}
        <div className="card">
          <p className="text-xs text-text-muted mb-4 uppercase tracking-wider">Confidence distribution</p>
          {data.active === 0
            ? <EmptyState msg="No active entries" />
            : (
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie data={confDist} dataKey="value" cx="50%" cy="50%" outerRadius={60} paddingAngle={3}>
                    {confDist.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#12121f', border: '1px solid #1e1e35', borderRadius: 8, fontSize: 12 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: '#9090b0' }} />
                </PieChart>
              </ResponsiveContainer>
            )}
        </div>
      </div>

      {/* Top used */}
      {data.top_used.length > 0 && (
        <div className="card">
          <p className="text-xs text-text-muted mb-3 uppercase tracking-wider">Most-used entries</p>
          <div className="space-y-2">
            {data.top_used.map(e => (
              <div key={e.id} className="flex items-center gap-3 text-sm">
                <span className="font-mono text-xs text-text-muted w-5 text-right">{e.use_count}×</span>
                <span className="flex-1 text-text-secondary truncate">{e.title}</span>
                <span className="badge border border-bg-border text-text-muted">{e.type.replace('_', ' ')}</span>
                <span className="text-xs text-orange-400">{(e.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}


function RunsSection() {
  const { data, loading, error } = useApi(() => api.runs(30), [], { interval: 15_000 })

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm font-semibold text-text-primary">Recent Runs</p>
        {loading && <Loader2 className="w-4 h-4 text-text-muted animate-spin" />}
      </div>
      {error && <div className="text-sm text-red-400 flex items-center gap-2 mb-3"><AlertTriangle className="w-4 h-4" />{error}</div>}
      {!loading && !data?.runs?.length
        ? <EmptyState msg="No pipeline runs yet. Trigger one via a PR or the API." />
        : (
          <div className="space-y-2">
            {(data?.runs ?? []).map((run, i) => (
              <div key={run.run_id ?? i} className="flex items-start gap-3 p-3 rounded-lg bg-bg-base hover:bg-bg-raised transition-colors">
                <div className="mt-0.5">{statusIcon[run.status] ?? <Clock className="w-4 h-4 text-text-muted" />}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-text-primary truncate">
                      {run.repo} <span className="text-text-muted">#{run.pr}</span>
                    </span>
                    {run.risk_level && (
                      <span className={`badge border text-xs ${riskBg[run.risk_level] ?? 'bg-bg-raised border-bg-border'}`}>
                        <span className={riskColor[run.risk_level] ?? 'text-text-muted'}>{run.risk_level}</span>
                      </span>
                    )}
                    {run.regressions != null && run.regressions > 0 && (
                      <span className="badge border border-red-500/40 bg-red-500/10 text-xs flex items-center gap-1 text-red-400">
                        <RotateCcw className="w-3 h-3" />
                        {run.regressions} regression{run.regressions !== 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 mt-1 text-xs text-text-muted flex-wrap">
                    {run.started_at && <span>{new Date(run.started_at).toLocaleString()}</span>}
                    {run.findings !== undefined && <span>{run.findings} findings</span>}
                    {run.auto_fixes !== undefined && <span>{run.auto_fixes} auto-fixed</span>}
                    {run.pending_fixes !== undefined && run.pending_fixes > 0 && (
                      <span className="text-amber-400">{run.pending_fixes} pending</span>
                    )}
                    {run.regressions != null && run.regressions > 0 && (
                      <span className="text-red-400 font-medium">
                        ⚠ {run.regressions} previously-fixed bug{run.regressions !== 1 ? 's' : ''} reintroduced
                      </span>
                    )}
                    {run.token_total != null && run.token_total > 0 && (
                      <span className="text-text-muted flex items-center gap-1">
                        <Zap className="w-3 h-3" />
                        {run.token_total.toLocaleString()} tokens
                        {run.est_cost_usd != null && run.est_cost_usd > 0 && (
                          <span className="text-text-muted"> · ~${run.est_cost_usd.toFixed(4)}</span>
                        )}
                      </span>
                    )}
                  </div>
                  {run.error && <div className="text-xs text-red-400 mt-1 truncate">{run.error}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
    </div>
  )
}


function ApprovalsSection() {
  const { data, loading, error, refetch } = useApi(() => api.approvals('pending'), [])
  const [acting, setActing] = useState<string | null>(null)

  const act = async (id: string, action: 'approve' | 'reject') => {
    setActing(id)
    try {
      if (action === 'approve') await api.approve(id)
      else await api.reject(id)
      await refetch()
    } finally {
      setActing(null)
    }
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm font-semibold text-text-primary">
          Pending Approvals
          {data && data.total > 0 && (
            <span className="ml-2 badge bg-amber-500/15 border border-amber-500/30 text-amber-400">
              {data.total}
            </span>
          )}
        </p>
        {loading && <Loader2 className="w-4 h-4 text-text-muted animate-spin" />}
      </div>

      {error && <div className="text-sm text-red-400 flex items-center gap-2"><AlertTriangle className="w-4 h-4" />{error}</div>}
      {!loading && !data?.approvals?.length
        ? <EmptyState msg="No pending approvals. All fixes are either auto-applied or awaiting a PR trigger." />
        : (
          <div className="space-y-3">
            {(data?.approvals ?? []).map(a => (
              <div key={a.id} className="rounded-lg border border-bg-border bg-bg-base p-4">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">{a.description}</p>
                    <p className="text-xs text-text-muted mt-0.5">
                      {a.repo} #{a.pr} · {new Date(a.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => act(a.id, 'approve')}
                      disabled={acting === a.id}
                      className="btn-primary py-1 px-3 text-xs"
                    >
                      {acting === a.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
                      Approve
                    </button>
                    <button
                      onClick={() => act(a.id, 'reject')}
                      disabled={acting === a.id}
                      className="btn-secondary py-1 px-3 text-xs"
                    >
                      <XCircle className="w-3 h-3" />
                      Reject
                    </button>
                  </div>
                </div>
                {a.rationale && <p className="text-xs text-text-muted italic mb-2">{a.rationale}</p>}
                <div className="flex flex-wrap gap-1.5">
                  {a.affected_files.map(f => (
                    <span key={f} className="font-mono text-xs px-2 py-0.5 rounded bg-bg-raised border border-bg-border text-text-muted">{f}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
    </div>
  )
}


function AgentsSection() {
  const { data, loading, error, refetch } = useApi(() => api.agentStatus(), [], { interval: 60_000 })
  const [triggering, setTriggering] = useState<string | null>(null)
  const [triggerRepo, setTriggerRepo] = useState('')
  const [triggerPR, setTriggerPR] = useState('')
  const [pipelineMsg, setPipelineMsg] = useState('')

  const triggerAgent = async (agentId: string) => {
    setTriggering(agentId)
    try {
      await api.triggerMaintenance(agentId)
      setTimeout(refetch, 2000)
    } finally {
      setTriggering(null)
    }
  }

  const triggerAll = () => triggerAgent('all')

  const triggerPipeline = async () => {
    if (!triggerRepo || !triggerPR) return
    try {
      await api.triggerPipeline(triggerRepo, parseInt(triggerPR))
      setPipelineMsg('Pipeline triggered! Check Runs section for status.')
      setTriggerRepo(''); setTriggerPR('')
    } catch {
      setPipelineMsg('Failed to trigger. Check server logs.')
    }
  }

  return (
    <div className="space-y-4">
      {/* Manual pipeline trigger */}
      <div className="card">
        <p className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
          <Play className="w-4 h-4 text-orange-400" /> Run Pipeline Manually
        </p>
        <div className="flex gap-2 flex-wrap">
          <input
            value={triggerRepo}
            onChange={e => setTriggerRepo(e.target.value)}
            placeholder="owner/repo"
            className="flex-1 min-w-32 bg-bg-base border border-bg-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-orange-500"
          />
          <input
            value={triggerPR}
            onChange={e => setTriggerPR(e.target.value)}
            placeholder="PR #"
            type="number"
            className="w-24 bg-bg-base border border-bg-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-orange-500"
          />
          <button onClick={triggerPipeline} className="btn-primary">
            <Play className="w-3.5 h-3.5" /> Run
          </button>
        </div>
        {pipelineMsg && <p className="text-xs text-orange-400 mt-2">{pipelineMsg}</p>}
      </div>

      {/* Maintenance agents */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-text-muted" /> Maintenance Agents
          </p>
          <button
            onClick={triggerAll}
            disabled={triggering === 'all'}
            className="btn-secondary text-xs py-1.5"
          >
            {triggering === 'all' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Run All Now
          </button>
        </div>

        {loading && <div className="py-4"><Spinner /></div>}
        {error && <div className="text-sm text-red-400">{error}</div>}

        {data && (
          <div className="space-y-2">
            {data.agents.map(agent => (
              <div key={agent.id} className="flex items-start gap-3 p-3 rounded-lg bg-bg-base">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-text-primary">{agent.name}</span>
                    <span className="badge border border-bg-border text-text-muted text-xs">{agent.schedule}</span>
                  </div>
                  <p className="text-xs text-text-muted mt-0.5">{agent.role}</p>
                  {agent.last_run && (
                    <p className="text-xs text-text-muted mt-1">
                      Last run: {new Date(agent.last_run).toLocaleString()}
                      {agent.last_result && typeof agent.last_result === 'object' && (
                        <span className="ml-2">
                          {Object.entries(agent.last_result)
                            .filter(([k]) => !['ran_at', 'agent'].includes(k))
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(' · ')}
                        </span>
                      )}
                    </p>
                  )}
                  {!agent.last_run && <p className="text-xs text-text-muted mt-1 italic">Never run</p>}
                </div>
                <button
                  onClick={() => triggerAgent(agent.id)}
                  disabled={!!triggering}
                  className="btn-ghost text-xs py-1 px-2 shrink-0"
                >
                  {triggering === agent.id
                    ? <Loader2 className="w-3 h-3 animate-spin" />
                    : <Play className="w-3 h-3" />}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}


const severityBg: Record<string, string> = {
  high:   'bg-red-500/10 border-red-500/30',
  medium: 'bg-amber-500/10 border-amber-500/30',
  low:    'bg-white/5 border-white/20',
}
const severityText: Record<string, string> = {
  high:   'text-red-400',
  medium: 'text-amber-400',
  low:    'text-text-muted',
}
const patternIcon: Record<string, string> = {
  recurring_category:   '🔄',
  high_regression_rate: '🐛',
  high_finding_volume:  '📊',
  systemic_kb_entry:    '📌',
  file_area_hotspot:    '🎯',
  elevated_risk_trend:  '⚡',
}

function PatternsSection() {
  const { data, loading, error, refetch } = useApi(() => api.patterns(), [], { interval: 120_000 })
  const [triggering, setTriggering] = useState(false)
  const [msg, setMsg] = useState('')

  const runDetector = async () => {
    setTriggering(true)
    try {
      await api.triggerMaintenance('pattern_detector')
      setMsg('Pattern detection running… refresh in ~30 s.')
      setTimeout(() => { refetch(); setMsg('') }, 35_000)
    } finally {
      setTriggering(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-text-muted uppercase tracking-wider">Cross-PR patterns</p>
        <button
          onClick={runDetector}
          disabled={triggering}
          className="btn-secondary text-xs py-1.5"
        >
          {triggering ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Detect Now
        </button>
      </div>
      {msg && <p className="text-xs text-orange-400">{msg}</p>}
      {loading && <div className="card"><Spinner /></div>}
      {error && (
        <div className="card text-sm text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      )}
      {!loading && !data?.patterns?.length && (
        <div className="card">
          <EmptyState msg="No patterns detected yet. Run the pattern detector or wait for enough pipeline runs to accumulate." />
        </div>
      )}
      {(data?.patterns ?? []).map((p, i) => (
        <div key={i} className={`card border ${severityBg[p.severity] ?? 'bg-bg-raised border-bg-border'}`}>
          <div className="flex items-start gap-3">
            <span className="text-xl shrink-0 mt-0.5">{patternIcon[p.type] ?? '📋'}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <span className="text-sm font-semibold text-text-primary">{p.title}</span>
                <span className={`badge border text-xs ${severityBg[p.severity]} ${severityText[p.severity]}`}>
                  {p.severity}
                </span>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">{p.description}</p>
              {Object.keys(p.evidence).length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {Object.entries(p.evidence).slice(0, 3).map(([k, v]) => (
                    <span key={k} className="font-mono text-xs px-2 py-0.5 rounded bg-bg-raised border border-bg-border text-text-muted">
                      {k.replace(/_/g, ' ')}: {String(v)}
                    </span>
                  ))}
                </div>
              )}
              <p className="text-xs text-text-muted mt-2">{new Date(p.detected_at).toLocaleString()}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}



// ── Connect Banner ────────────────────────────────────────────────────────────

function ConnectBanner({
  onConnect,
}: {
  onConnect: (url: string) => void
}) {
  const [url, setUrl] = useState(getBackendUrl())
  const [testing, setTesting] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function handleConnect() {
    setTesting(true)
    setErr(null)
    const clean = url.replace(/\/+$/, '')
    try {
      const res = await fetch(clean + '/api/status', {
        signal: AbortSignal.timeout(5000),
        headers: { 'ngrok-skip-browser-warning': 'true' },
      })
      if (!res.ok) throw new Error(`Server returned ${res.status}`)
      setBackendUrl(clean)
      onConnect(clean)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not reach server')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="mb-6 rounded-xl border border-orange-500/30 bg-orange-500/5 p-5">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-orange-400 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white mb-1">Connect to your SENTINEL instance</p>
          <p className="text-xs text-text-muted mb-3">
            Run <code className="bg-bg-raised px-1.5 py-0.5 rounded text-orange-300">sentinel serve</code> locally,
            then paste the URL below. Use <code className="bg-bg-raised px-1.5 py-0.5 rounded text-orange-300">ngrok http 8000</code> to expose it remotely.
          </p>
          <div className="flex gap-2 flex-wrap">
            <input
              type="url"
              value={url}
              onChange={e => setUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleConnect()}
              placeholder="http://localhost:8000"
              className="flex-1 min-w-0 bg-bg-raised border border-bg-border rounded-lg px-3 py-2 text-sm text-white placeholder:text-text-muted focus:outline-none focus:border-orange-500/50 font-mono"
            />
            <button
              onClick={handleConnect}
              disabled={testing || !url}
              className="px-4 py-2 text-sm font-medium bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white rounded-lg transition-colors flex items-center gap-2 shrink-0"
            >
              {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {testing ? 'Connecting…' : 'Connect'}
            </button>
          </div>
          {err && <p className="mt-2 text-xs text-red-400">{err}</p>}
        </div>
      </div>
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

type Tab = 'overview' | 'runs' | 'approvals' | 'agents' | 'patterns'

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>('overview')
  const [backendUrl, setBackendUrlState] = useState<string | null>(() => {
    // Try to detect if a URL is already saved by checking connectivity on mount
    return localStorage.getItem('sentinel_backend_url')
  })
  const [connected, setConnected] = useState(false)
  const { data: status, error: statusError } = useApi(() => api.status(), [backendUrl], { interval: 30_000 })

  useEffect(() => {
    setConnected(!!status)
  }, [status])

  function handleConnect(url: string) {
    setBackendUrlState(url)
    setConnected(true)
  }

  function handleDisconnect() {
    clearBackendUrl()
    setBackendUrlState(null)
    setConnected(false)
  }

  const tabs: { id: Tab; label: string; icon: typeof Activity }[] = [
    { id: 'overview',  label: 'KB Health',       icon: Database },
    { id: 'runs',      label: 'Run History',      icon: Activity },
    { id: 'approvals', label: 'Approvals',        icon: CheckCircle2 },
    { id: 'agents',    label: 'Agents',           icon: RefreshCw },
    { id: 'patterns',  label: 'Patterns',         icon: TrendingUp },
  ]

  return (
    <div className="max-w-6xl mx-auto px-4 py-10">
      {/* Header */}
      <div className="flex items-start justify-between mb-8 gap-4 flex-wrap">
        <div>
          <p className="section-label mb-1">Management</p>
          <h1 className="font-display font-black text-white" style={{ fontSize: 'clamp(2rem,3.5vw,3rem)' }}>dashboard</h1>
        </div>
        <div className="flex items-center gap-3">
          {connected && status && (
            <>
              <div className="flex items-center gap-2">
                <span className={clsx(
                  'w-2 h-2 rounded-full animate-pulse-slow',
                  status.status === 'healthy' ? 'bg-white' : 'bg-amber-400'
                )} />
                <span className="text-xs text-text-muted">
                  {status.status === 'healthy' ? 'System healthy' : 'Degraded'} ·{' '}
                  {status.kb.entries} KB entries ·{' '}
                  LLM: {status.llm_provider}
                </span>
              </div>
              <button
                onClick={handleDisconnect}
                className="text-xs text-text-muted hover:text-red-400 transition-colors"
                title="Disconnect"
              >
                disconnect
              </button>
            </>
          )}
        </div>
      </div>

      {/* Connect banner */}
      {!connected && <ConnectBanner onConnect={handleConnect} />}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-bg-border">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-all duration-150',
              tab === id
                ? 'border-orange-500 text-orange-400'
                : 'border-transparent text-text-muted hover:text-text-secondary'
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Content — only render sections after connected to avoid hitting localhost */}
      <div className="animate-fade-in">
        {connected ? (
          <>
            {tab === 'overview'  && <KBHealthSection />}
            {tab === 'runs'      && <RunsSection />}
            {tab === 'approvals' && <ApprovalsSection />}
            {tab === 'agents'    && <AgentsSection />}
            {tab === 'patterns'  && <PatternsSection />}
          </>
        ) : (
          <div className="py-16 text-center text-sm text-text-muted">
            Connect to your SENTINEL instance above to view data.
          </div>
        )}
      </div>
    </div>
  )
}
