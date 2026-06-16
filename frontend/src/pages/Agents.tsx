import { useState } from 'react'
import clsx from 'clsx'

interface Agent {
  name: string
  role: string
  detail: string
  inputs: string[]
  outputs: string[]
}

interface Swarm {
  id: string
  label: string
  execution: 'parallel' | 'sequential' | 'conditional' | 'scheduled'
  agents: Agent[]
}

const swarms: Swarm[] = [
  {
    id: 'triage',
    label: 'triage',
    execution: 'sequential',
    agents: [
      {
        name: 'risk-scoring agent',
        role: 'sets pipeline depth for the entire run',
        detail: 'runs first on every pr. combines a deterministic heuristic pre-score (diff volume, sensitive file paths) with an llm score to produce a low / medium / high label. tiny non-sensitive prs are short-circuited without an llm call.',
        inputs: ['pr diff', 'file list', 'additions / deletions count'],
        outputs: ['riskscore (level, score, reasons, sensitive_areas)'],
      },
    ],
  },
  {
    id: 'review',
    label: 'review swarm',
    execution: 'parallel',
    agents: [
      {
        name: 'security agent',
        role: 'finds vulnerabilities in changed code',
        detail: 'runs a regex pre-scan for hardcoded secrets before any llm call. then uses the strong model to find injection risks (sql, command, ldap, template), auth/authorization flaws, unsafe deserialization, weak crypto, ssrf, path traversal, xss, and csrf.',
        inputs: ['diff', 'kb security findings'],
        outputs: ['security_findings: list[reviewfinding]'],
      },
      {
        name: 'performance agent',
        role: 'catches n+1 queries and blocking async calls',
        detail: 'analyses added/modified lines for n+1 query patterns in orm loops, unbounded queries without pagination, blocking sync i/o inside async functions, o(n²) algorithms, string concatenation in loops, and repeated identical db calls without caching.',
        inputs: ['diff', 'kb performance patterns'],
        outputs: ['performance_findings: list[reviewfinding]'],
      },
      {
        name: 'style agent',
        role: 'enforces conventions and code quality',
        detail: 'checks naming (snake_case, pascalcase, screaming_snake), bare excepts, mutable defaults, import*, boolean parameter flags, overly long functions, missing type annotations, magic numbers, commented-out code, and todos without ticket references.',
        inputs: ['diff', 'kb codebase patterns'],
        outputs: ['style_findings: list[reviewfinding]'],
      },
      {
        name: 'architecture agent',
        role: 'checks design and module boundaries (medium+ risk only)',
        detail: 'skipped on low-risk prs. looks for layering violations, circular dependencies, god classes, tight coupling, feature envy, missing abstractions, public api changes without deprecation paths, and business logic leaking into the data layer.',
        inputs: ['diff (medium/high risk only)', 'kb architecture patterns'],
        outputs: ['architecture_findings: list[reviewfinding]'],
      },
      {
        name: 'lead reviewer',
        role: 'consolidates and de-duplicates all specialist findings',
        detail: 'receives the combined output of all four specialists. removes exact or near-duplicate findings, merges overlapping comments about the same file/line, re-prioritises by severity and business impact, and attaches a one-sentence rationale to each finding.',
        inputs: ['security + performance + style + architecture findings'],
        outputs: ['consolidated_findings: list[reviewfinding]'],
      },
    ],
  },
  {
    id: 'test',
    label: 'test swarm',
    execution: 'sequential',
    agents: [
      {
        name: 'per-module test agent',
        role: 'generates unit tests for each changed source file',
        detail: 'filters changed files to testable source files. for each file, extracts its diff section and asks the llm to write tests covering the happy path plus at least two edge cases per new/modified function. matches the project\'s existing testing framework.',
        inputs: ['diff per module', 'kb test patterns'],
        outputs: ['generated_tests: list[generatedtest]'],
      },
      {
        name: 'coverage analysis agent',
        role: 'identifies uncovered branches after test execution',
        detail: 'parses pytest-cov output from the sandbox to find files with coverage below 80%. updates coverage_gaps with specific module/line targets. these gaps are surfaced in the pr comment to guide the developer.',
        inputs: ['test_results (stdout with coverage report)'],
        outputs: ['coverage_gaps: list[str]', 'updated coverage_percent per module'],
      },
      {
        name: 'integration test agent',
        role: 'tests cross-module interactions (medium+ risk)',
        detail: 'only fires when risk is medium or high and multiple source files were changed and at least one changed file imports another changed file. writes tests that exercise data flows across module boundaries, error propagation, and end-to-end happy paths.',
        inputs: ['diff', 'list of changed modules (medium/high risk only)'],
        outputs: ['appends one generatedtest to generated_tests'],
      },
    ],
  },
  {
    id: 'bug_squad',
    label: 'bug-hunting strike team',
    execution: 'conditional',
    agents: [
      {
        name: 'reproduction agent',
        role: 'isolates each failing test into a minimal repro',
        detail: 'takes the failing test name, stdout, and stderr from the sandbox and asks the llm to strip everything that doesn\'t contribute to the failure. produces a self-contained script that reproduces the exact assertion error with minimal imports.',
        inputs: ['failing_tests list', 'stdout/stderr from sandbox', 'pr diff'],
        outputs: ['bug_reports (bugreport with minimal_repro)'],
      },
      {
        name: 'root-cause agent',
        role: 'traces the failure to its source',
        detail: 'uses the strong model to reason over the minimal repro, the pr diff, and similar past bugs from the kb. produces a precise root-cause explanation identifying the likely source file and line, and a one-sentence hypothesis to guide the fix.',
        inputs: ['minimal_repro', 'pr diff', 'kb bug_fix entries'],
        outputs: ['updated bugreport with root_cause and affected_files'],
      },
      {
        name: 'fix-proposer agent',
        role: 'drafts 1–3 candidate patches',
        detail: 'queries the kb for similar past fixes first — if a known pattern exists, it prefers that approach. then generates up to 3 patches ordered by confidence. each patch is a standard unified diff compatible with git apply. patches are minimal.',
        inputs: ['root_cause', 'pr diff', 'kb bug_fix entries (past patches)'],
        outputs: ['candidate_patches: list[dict] ordered by confidence'],
      },
      {
        name: 'verification agent',
        role: 'runs each patch through the sandbox, selects the winner',
        detail: 'applies each candidate patch in the docker sandbox (network_mode=none, non-root) and runs the full test suite. selects the first patch that passes with no new test failures. classifies the selected patch as auto_merge or human_required.',
        inputs: ['candidate_patches', 'docker sandbox'],
        outputs: ['selected_patch', 'proposed_fixes with classification'],
      },
    ],
  },
  {
    id: 'trust',
    label: 'trust layer',
    execution: 'sequential',
    agents: [
      {
        name: 'explainability agent',
        role: 'attaches plain-english rationale to every finding and fix',
        detail: 'for every consolidated review finding and proposed fix, asks the fast model to generate a 2–3 sentence explanation answering: what is the issue, why does it matter, and what was changed. lets a human reviewer understand sentinel\'s reasoning without reading agent logs.',
        inputs: ['consolidated_findings', 'proposed_fixes'],
        outputs: ['findings and fixes with rationale field populated'],
      },
      {
        name: 'approval gate',
        role: 'classifies fixes and builds the pr comment',
        detail: 'classifies each proposed fix as auto_merge (small patch, non-sensitive files, not high-risk pr) or human_required (auth/payment/migration/api changes, large patches, high-risk prs). then assembles the consolidated pr comment summarising risk, findings by severity, test coverage, and applied/pending fixes.',
        inputs: ['proposed_fixes', 'consolidated_findings', 'risk', 'test_results'],
        outputs: ['auto_applied_fixes', 'pending_human_fixes', 'pr_comment (markdown)'],
      },
    ],
  },
  {
    id: 'self_healing',
    label: 'self-healing kb',
    execution: 'scheduled',
    agents: [
      {
        name: 'curator agent',
        role: 'removes stale and rejected entries (nightly)',
        detail: 'scans all active kb entries. invalidates entries linked to reverted commits. invalidates entries rejected 3+ times by humans. applies exponential confidence decay to entries not used recently. archives entries whose confidence drops below threshold (default 0.3).',
        inputs: ['all kb entries', 'reverted commit shas (from push events)'],
        outputs: ['invalidated / archived entries with reasons logged'],
      },
      {
        name: 'drift-checker agent',
        role: 'archives entries whose code has changed (nightly)',
        detail: 'for every kb entry that has a stored code snapshot hash, computes the sha-256 of the current file contents at the same paths. if the hash differs materially, archives the entry. prevents the kb from recommending fixes based on code that no longer exists.',
        inputs: ['kb entries with code_snapshot_hash', 'local repo path'],
        outputs: ['archived entries with drift reason'],
      },
      {
        name: 'consistency agent',
        role: 'resolves contradictions between kb entries (weekly)',
        detail: 'finds pairs of semantically similar entries (cosine similarity > 0.85). for each pair, asks the llm whether they contradict each other. if yes, deprecates the older or lower-confidence entry. capped at 50 llm comparisons per run to control cost.',
        inputs: ['all active kb entries'],
        outputs: ['invalidated contradicting entries'],
      },
      {
        name: 'consolidation agent',
        role: 'merges near-duplicate entries into patterns (weekly)',
        detail: 'clusters entries with cosine similarity > 0.90 into groups of 3+. for each cluster, generates a single canonical "generalised pattern" entry that captures the common thread. marks all cluster members as superseded_by the canonical entry. only runs when kb has 50+ entries.',
        inputs: ['all active kb entries (50+ required)'],
        outputs: ['new canonical entries + superseded originals'],
      },
    ],
  },
]

const execBadge: Record<string, string> = {
  parallel:    'parallel',
  sequential:  'sequential',
  conditional: 'on failure only',
  scheduled:   'scheduled',
}

function AgentCard({ agent }: { agent: Agent }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-bg-border">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-start justify-between gap-4 px-5 py-4 text-left hover:bg-bg-surface transition-colors duration-150"
      >
        <div className="flex-1 min-w-0">
          <p className="font-mono text-sm text-white font-medium">{agent.name}</p>
          <p className="font-mono text-xs text-text-muted mt-0.5">{agent.role}</p>
        </div>
        <span className="font-mono text-xs text-text-muted shrink-0 mt-0.5">
          {open ? '[-]' : '[+]'}
        </span>
      </button>

      {open && (
        <div className="border-t border-bg-border px-5 py-5 space-y-4 animate-fade-in bg-bg-surface">
          <p className="font-mono text-xs text-text-secondary leading-relaxed">{agent.detail}</p>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <p className="section-label mb-2">inputs</p>
              <div className="space-y-1">
                {agent.inputs.map(i => (
                  <div key={i} className="font-mono text-xs text-text-secondary bg-bg-base border border-bg-border px-2.5 py-1.5">
                    {i}
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="section-label mb-2">outputs</p>
              <div className="space-y-1">
                {agent.outputs.map(o => (
                  <div key={o} className="font-mono text-xs text-text-secondary bg-bg-base border border-bg-border px-2.5 py-1.5">
                    {o}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Agents() {
  const totalAgents = swarms.reduce((acc, s) => acc + s.agents.length, 0)

  return (
    <div className="max-w-4xl mx-auto px-6 py-12">

      {/* Header */}
      <div className="mb-12">
        <p className="section-label mb-3">reference</p>
        <h1 className="font-display font-black text-white mb-3" style={{ fontSize: 'clamp(2rem,3.5vw,3rem)' }}>agents</h1>
        <p className="text-text-muted text-sm font-mono">
          {totalAgents} agents across {swarms.length} swarms. click any agent to expand its full specification.
        </p>
      </div>

      {/* Swarms */}
      <div className="space-y-10">
        {swarms.map(swarm => (
          <div key={swarm.id} className="border border-bg-border">
            {/* Swarm header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-bg-border bg-bg-surface">
              <div className="flex items-center gap-4">
                <span className="font-mono text-sm font-semibold text-white">{swarm.label}</span>
                <span className="font-mono text-xs text-text-muted">
                  {swarm.agents.length} agent{swarm.agents.length > 1 ? 's' : ''}
                </span>
              </div>
              <span className="font-mono text-xs text-text-muted border border-bg-border px-2 py-0.5">
                {execBadge[swarm.execution]}
              </span>
            </div>

            {/* Agent cards */}
            <div className="divide-y divide-bg-border">
              {swarm.agents.map(agent => (
                <AgentCard key={agent.name} agent={agent} />
              ))}
            </div>
          </div>
        ))}
      </div>

    </div>
  )
}
