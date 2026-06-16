import { Link } from 'react-router-dom'

/* ── SVG Icons ──────────────────────────────────────────────────────────────── */

function IconSecurity() {
  return (
    <svg viewBox="0 0 160 160" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
      {/* Shield */}
      <path d="M80 18 L132 42 L132 90 Q132 134 80 150 Q28 134 28 90 L28 42 Z" stroke="white" strokeWidth="1.4" opacity="0.9"/>
      {/* Lock body */}
      <rect x="60" y="84" width="40" height="34" rx="3" stroke="white" strokeWidth="1.4"/>
      {/* Lock shackle */}
      <path d="M67 84 L67 72 Q67 58 80 58 Q93 58 93 72 L93 84" stroke="white" strokeWidth="1.4"/>
      {/* Keyhole */}
      <circle cx="80" cy="97" r="5" stroke="white" strokeWidth="1.4"/>
      <line x1="80" y1="102" x2="80" y2="110" stroke="white" strokeWidth="1.4"/>
      {/* Side circuit nodes */}
      <circle cx="14" cy="70" r="3" stroke="white" strokeWidth="1" opacity="0.35"/>
      <line x1="17" y1="70" x2="28" y2="70" stroke="white" strokeWidth="1" opacity="0.35"/>
      <circle cx="146" cy="70" r="3" stroke="white" strokeWidth="1" opacity="0.35"/>
      <line x1="132" y1="70" x2="143" y2="70" stroke="white" strokeWidth="1" opacity="0.35"/>
      {/* Top circuit lines */}
      <line x1="80" y1="8" x2="80" y2="18" stroke="white" strokeWidth="1" opacity="0.25"/>
      <circle cx="80" cy="6" r="2" stroke="white" strokeWidth="1" opacity="0.25"/>
    </svg>
  )
}

function IconAgents() {
  return (
    <svg viewBox="0 0 160 160" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
      {/* Central hub */}
      <rect x="66" y="66" width="28" height="28" rx="4" stroke="white" strokeWidth="1.5"/>
      <line x1="74" y1="80" x2="86" y2="80" stroke="white" strokeWidth="1.2"/>
      <line x1="80" y1="74" x2="80" y2="86" stroke="white" strokeWidth="1.2"/>
      {/* Agent nodes — surrounding */}
      <rect x="16" y="20" width="26" height="22" rx="3" stroke="white" strokeWidth="1.2" opacity="0.8"/>
      <line x1="22" y1="31" x2="30" y2="31" stroke="white" strokeWidth="1" opacity="0.6"/>
      <rect x="118" y="20" width="26" height="22" rx="3" stroke="white" strokeWidth="1.2" opacity="0.8"/>
      <line x1="124" y1="31" x2="132" y2="31" stroke="white" strokeWidth="1" opacity="0.6"/>
      <rect x="16" y="119" width="26" height="22" rx="3" stroke="white" strokeWidth="1.2" opacity="0.8"/>
      <line x1="22" y1="130" x2="30" y2="130" stroke="white" strokeWidth="1" opacity="0.6"/>
      <rect x="118" y="119" width="26" height="22" rx="3" stroke="white" strokeWidth="1.2" opacity="0.8"/>
      <line x1="124" y1="130" x2="132" y2="130" stroke="white" strokeWidth="1" opacity="0.6"/>
      <rect x="67" y="16" width="26" height="22" rx="3" stroke="white" strokeWidth="1.2" opacity="0.8"/>
      <line x1="73" y1="27" x2="81" y2="27" stroke="white" strokeWidth="1" opacity="0.6"/>
      {/* Connectors */}
      <line x1="42" y1="31" x2="60" y2="60" stroke="white" strokeWidth="1" opacity="0.4" strokeDasharray="4 3"/>
      <line x1="118" y1="31" x2="100" y2="60" stroke="white" strokeWidth="1" opacity="0.4" strokeDasharray="4 3"/>
      <line x1="42" y1="130" x2="60" y2="100" stroke="white" strokeWidth="1" opacity="0.4" strokeDasharray="4 3"/>
      <line x1="118" y1="130" x2="100" y2="100" stroke="white" strokeWidth="1" opacity="0.4" strokeDasharray="4 3"/>
      <line x1="80" y1="38" x2="80" y2="66" stroke="white" strokeWidth="1" opacity="0.4" strokeDasharray="4 3"/>
    </svg>
  )
}

function IconKnowledgeBase() {
  return (
    <svg viewBox="0 0 160 160" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
      {/* Three database cylinders stacked */}
      <ellipse cx="80" cy="36" rx="34" ry="10" stroke="white" strokeWidth="1.4"/>
      <line x1="46" y1="36" x2="46" y2="62" stroke="white" strokeWidth="1.4"/>
      <line x1="114" y1="36" x2="114" y2="62" stroke="white" strokeWidth="1.4"/>
      <ellipse cx="80" cy="62" rx="34" ry="10" stroke="white" strokeWidth="1.4"/>

      <ellipse cx="80" cy="80" rx="34" ry="10" stroke="white" strokeWidth="1.4" opacity="0.7"/>
      <line x1="46" y1="80" x2="46" y2="106" stroke="white" strokeWidth="1.4" opacity="0.7"/>
      <line x1="114" y1="80" x2="114" y2="106" stroke="white" strokeWidth="1.4" opacity="0.7"/>
      <ellipse cx="80" cy="106" rx="34" ry="10" stroke="white" strokeWidth="1.4" opacity="0.7"/>

      {/* Horizontal data lines inside top cylinder */}
      <line x1="60" y1="48" x2="100" y2="48" stroke="white" strokeWidth="1" opacity="0.35"/>
      <line x1="64" y1="54" x2="96" y2="54" stroke="white" strokeWidth="1" opacity="0.35"/>

      {/* Lightning bolt — self-healing indicator */}
      <path d="M84 115 L76 130 L82 130 L78 148 L90 130 L84 130 Z" stroke="white" strokeWidth="1.3" fill="none" opacity="0.8"/>

      {/* Arrow up — knowledge flowing */}
      <path d="M124 90 L132 82 L140 90" stroke="white" strokeWidth="1.2" opacity="0.4"/>
      <line x1="132" y1="82" x2="132" y2="106" stroke="white" strokeWidth="1.2" opacity="0.4"/>
    </svg>
  )
}

function IconSelfHealing() {
  return (
    <svg viewBox="0 0 160 160" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
      {/* Large circular arrow — outer */}
      <path d="M80 22 A58 58 0 1 1 28 100" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
      {/* Arrowhead */}
      <polyline points="14,90 28,100 38,88" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>

      {/* Inner circular arrow — opposite direction */}
      <path d="M80 50 A30 30 0 1 0 50 80" stroke="white" strokeWidth="1.3" strokeLinecap="round" opacity="0.55"/>
      <polyline points="62,68 50,80 62,90" stroke="white" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" opacity="0.55"/>

      {/* Center gear-ish — hexagon */}
      <path d="M80 68 L88 72 L88 82 L80 86 L72 82 L72 72 Z" stroke="white" strokeWidth="1.3"/>
      <circle cx="80" cy="77" r="4" stroke="white" strokeWidth="1.2"/>
    </svg>
  )
}

/* ── Pipeline node component ───────────────────────────────────────────────── */

type NodeKind = 'default' | 'trigger' | 'ai' | 'output'

function PNode({
  label, sub, kind = 'default'
}: { label: string; sub?: string; kind?: NodeKind }) {
  const border = kind === 'trigger' ? 'border-orange-500/60' :
                 kind === 'ai'      ? 'border-orange-400/40' :
                 kind === 'output'  ? 'border-orange-500/50' :
                                     'border-bg-border'
  return (
    <div className={`border ${border} bg-bg-raised px-3 py-2 min-w-[100px] shrink-0`}>
      <div className="font-mono text-[10px] text-white/80 leading-tight">{label}</div>
      {sub && <div className="font-mono text-[9px] text-text-muted mt-0.5">{sub}</div>}
    </div>
  )
}

function Arrow({ vertical = false }: { vertical?: boolean }) {
  if (vertical) {
    return (
      <div className="flex justify-center py-1">
        <div className="w-px h-6 bg-bg-border relative">
          <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 text-text-muted text-[8px]">▼</span>
        </div>
      </div>
    )
  }
  return (
    <div className="flex items-center px-1 shrink-0">
      <div className="h-px w-5 bg-bg-border" />
      <span className="text-text-muted text-[8px] -ml-0.5">▶</span>
    </div>
  )
}

/* ── Data ───────────────────────────────────────────────────────────────────── */

const iconCards = [
  {
    icon: <IconSecurity />,
    title: 'Secure Execution',
    desc: 'Every code run happens inside a Docker container: network disabled, non-root uid 1000, memory-capped. HMAC-SHA256 verifies every webhook before any payload is parsed.',
  },
  {
    icon: <IconAgents />,
    title: 'Agent Build',
    desc: '19 specialized agents built on LangGraph. Each swarm fires in parallel — security, performance, style, architecture, and test agents all run simultaneously per PR.',
  },
  {
    icon: <IconKnowledgeBase />,
    title: 'Knowledge at Scale',
    desc: 'ChromaDB + SBERT power a local vector store that accumulates every finding and fix from your codebase history. No cloud. No data leaves your machine.',
  },
  {
    icon: <IconSelfHealing />,
    title: 'Self-Healing',
    desc: 'Nightly maintenance agents prune stale KB entries, consolidate duplicates, check for codebase drift, and apply exponential confidence decay — automatically.',
  },
]

const features = [
  {
    n: '01', title: 'risk-aware routing', tag: 'risk scorer',
    body: 'Every PR is scored on impact, complexity, and path sensitivity before a single agent fires. Low-risk PRs get a fast-lane review. High-risk PRs trigger the full 19-agent pipeline.',
  },
  {
    n: '02', title: 'five specialized swarms', tag: 'langgraph',
    body: 'Review, Test, Bug Squad, Trust Layer, Self-Healing — each swarm is a LangGraph fan-out of parallel specialist agents. Results are synthesized by a lead agent before merging back.',
  },
  {
    n: '03', title: 'hardened docker sandbox', tag: 'security',
    body: "Every code execution runs inside a container: network disabled, non-root uid 1000, memory-capped, hard timeout enforced. Your host machine never touches PR code.",
  },
  {
    n: '04', title: 'knowledge base that learns', tag: 'self-healing',
    body: 'Chroma + SBERT power a vector store that accumulates every finding, fix, and pattern. Nightly maintenance agents prune drift, consolidate duplicates, and decay stale entries.',
  },
]

const pipelineSteps = [
  { n: '01', label: 'pr opened' },
  { n: '02', label: 'risk scored' },
  { n: '03', label: 'kb context' },
  { n: '04', label: 'review swarm' },
  { n: '05', label: 'test swarm' },
  { n: '06', label: 'bug squad' },
  { n: '07', label: 'trust gate' },
  { n: '08', label: 'review posted' },
]

const stats = [
  { n: '19', label: 'agents' },
  { n: '5',  label: 'swarms' },
  { n: '4',  label: 'kb healers' },
  { n: '<5s',label: 'avg per run' },
]

const capabilities = [
  { label: 'parallel review swarm',     sub: '5 agents fire simultaneously per PR' },
  { label: 'self-healing knowledge',    sub: 'kb grows smarter with every review' },
  { label: 'automated test generation', sub: 'missing coverage? agents write the tests' },
  { label: 'zero-trust approval gate',  sub: 'auth & payment paths always need a human' },
]

const techStack = [
  ['LangGraph','orchestration'], ['ChromaDB','vector store'],
  ['SBERT','embeddings'],        ['FastAPI','webhook server'],
  ['Docker','sandbox'],          ['APScheduler','cron jobs'],
  ['Claude API','llm (strong)'], ['Ollama','llm (local)'],
]

/* ── Page ───────────────────────────────────────────────────────────────────── */

export default function Home() {
  return (
    <div className="bg-bg-base">

      {/* ── Hero ──────────────────────────────────────────────────────── */}
      <section className="relative min-h-screen flex flex-col overflow-hidden">
        <div className="absolute inset-0 hero-bg" />
        <div className="absolute inset-0 hero-grid" />

        <div className="relative flex-1 flex items-start">
          <div className="max-w-7xl mx-auto px-6 w-full pt-36 pb-10">
            <div className="flex justify-end">
              <div className="flex flex-col w-full max-w-2xl">
                <p className="section-label mb-8">what sentinel does</p>
                {capabilities.map(({ label, sub }) => (
                  <div key={label} className="group flex items-start gap-5 py-5 border-b border-bg-border/50 last:border-0 cursor-default">
                    <span className="mt-2 w-1.5 h-1.5 rounded-full bg-bg-border group-hover:bg-orange-500 transition-colors duration-200 shrink-0" />
                    <div>
                      <div className="font-display font-bold text-white/25 group-hover:text-white transition-colors duration-200 leading-tight" style={{ fontSize: 'clamp(1.3rem,2.6vw,2.1rem)' }}>
                        {label}
                      </div>
                      <div className="font-mono text-xs text-text-muted mt-1.5 group-hover:text-text-secondary transition-colors">{sub}</div>
                    </div>
                  </div>
                ))}
                <div className="flex items-center gap-3 mt-7 flex-wrap">
                  <span className="font-mono text-xs text-text-muted">works with</span>
                  <span className="font-mono text-xs text-text-muted">→</span>
                  {['claude', 'ollama', 'github', 'chroma'].map(s => (
                    <span key={s} className="font-mono text-xs border border-bg-border px-2.5 py-1 text-text-muted hover:text-orange-400 hover:border-orange-500/40 transition-colors cursor-default">{s}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="relative max-w-7xl mx-auto px-6 pb-20 w-full">
          <div className="w-full h-px bg-bg-border mb-14" />
          <h1 className="font-display font-black text-white leading-[0.88] tracking-tight" style={{ fontSize: 'clamp(3rem,9vw,8.5rem)' }}>
            guards your<br />
            codebase.<br />
            <span className="text-orange-500">never sleeps.</span>
          </h1>
          <div className="mt-8 flex flex-col sm:flex-row gap-6 sm:items-start">
            <p className="font-mono text-sm text-text-muted max-w-xs leading-relaxed">
              19 agents. 5 swarms. self-healing knowledge base. open source and completely free.
            </p>
            <div className="flex gap-3 flex-wrap">
              <Link to="/docs" className="btn-primary">deploy sentinel →</Link>
              <Link to="/agents" className="btn-secondary">explore agents</Link>
            </div>
          </div>
          <div className="mt-16 flex flex-wrap gap-12 sm:gap-20">
            {stats.map(({ n, label }) => (
              <div key={label}>
                <div className="font-display font-black text-orange-400 leading-none" style={{ fontSize: 'clamp(2rem,4vw,3.5rem)' }}>{n}</div>
                <div className="font-mono text-xs text-text-muted mt-2">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Icon feature cards ─────────────────────────────────────────── */}
      <section className="border-t border-bg-border relative">
        <div className="absolute inset-0 hero-grid opacity-40" />
        <div className="relative max-w-7xl mx-auto px-6 pt-16 pb-0">
          <p className="section-label mb-2">capabilities</p>
        </div>
        <div className="relative grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-px bg-bg-border mt-8">
          {iconCards.map(({ icon, title, desc }) => (
            <div key={title} className="group bg-bg-base flex flex-col gap-0 hover:bg-bg-surface transition-colors duration-200 cursor-default">
              {/* Icon area */}
              <div className="h-52 flex items-center justify-center px-10 pt-10 pb-4 opacity-70 group-hover:opacity-100 transition-opacity duration-300">
                {icon}
              </div>
              {/* Text area */}
              <div className="px-8 pb-10 pt-2">
                <h3 className="font-mono font-bold text-sm text-white mb-3 tracking-wide">{title}</h3>
                <p className="font-mono text-xs text-text-secondary leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Pipeline visualization ─────────────────────────────────────── */}
      <section className="border-t border-bg-border">
        <div className="max-w-7xl mx-auto px-6 py-16">
          <p className="section-label mb-5">our pipeline</p>
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-12">
            <h2 className="font-display font-black text-white leading-[0.9]" style={{ fontSize: 'clamp(2rem,4.5vw,4rem)' }}>
              review logic<br />at scale.
            </h2>
            <p className="font-mono text-sm text-text-muted max-w-sm leading-relaxed">
              from a single github webhook to a full consolidated review comment — every pr runs through up to 19 specialized agents, automatically.
            </p>
          </div>
        </div>

        {/* Node graph */}
        <div className="relative border-t border-bg-border bg-bg-surface overflow-hidden">
          <div className="absolute inset-0 hero-grid opacity-50" />
          <div className="relative max-w-7xl mx-auto px-6 py-14">

            {/* Row 1: Trigger → sequential setup */}
            <div className="flex items-center flex-wrap gap-0 mb-0">
              <PNode label="PR Webhook" sub="pull_request event" kind="trigger" />
              <Arrow />
              <PNode label="Risk Scorer" sub="score: 0.00–1.00" />
              <Arrow />
              <PNode label="KB Fetch" sub="top-k context" kind="ai" />
              <Arrow />
              <div className="border border-dashed border-text-muted/25 px-2 py-1 shrink-0">
                <span className="font-mono text-[9px] text-text-muted uppercase tracking-widest">fan-out ↓</span>
              </div>
            </div>

            {/* Vertical connector to parallel box */}
            <div className="ml-[338px] w-px h-6 bg-bg-border" />

            {/* Row 2: Parallel swarms box */}
            <div className="border border-dashed border-orange-500/25 bg-orange-500/[0.03] p-4 inline-flex flex-col gap-3 min-w-[540px] max-w-full">
              <span className="font-mono text-[9px] text-orange-400/60 uppercase tracking-widest mb-1">parallel swarms — fire simultaneously</span>

              {/* Review swarm row */}
              <div className="flex items-center gap-0 flex-wrap">
                <span className="font-mono text-[9px] text-text-muted w-20 shrink-0">review</span>
                <PNode label="Security" kind="ai" />
                <Arrow />
                <PNode label="Performance" kind="ai" />
                <Arrow />
                <PNode label="Style" kind="ai" />
                <Arrow />
                <PNode label="Architecture" kind="ai" />
                <Arrow />
                <PNode label="Lead Review" kind="ai" />
              </div>

              {/* Test swarm row */}
              <div className="flex items-center gap-0 flex-wrap">
                <span className="font-mono text-[9px] text-text-muted w-20 shrink-0">tests</span>
                <PNode label="Module Tests" kind="ai" />
                <Arrow />
                <PNode label="Coverage" kind="ai" />
                <Arrow />
                <PNode label="Integration" kind="ai" />
              </div>

              {/* Bug squad row */}
              <div className="flex items-center gap-0 flex-wrap">
                <span className="font-mono text-[9px] text-text-muted w-20 shrink-0">bug squad</span>
                <PNode label="Reproduce" kind="ai" />
                <Arrow />
                <PNode label="Root Cause" kind="ai" />
                <Arrow />
                <PNode label="Fix Proposer" kind="ai" />
                <Arrow />
                <PNode label="Verify" kind="ai" />
              </div>
            </div>

            {/* Vertical connector from parallel box */}
            <div className="ml-[338px] w-px h-6 bg-bg-border" />

            {/* Row 3: Sequential output */}
            <div className="flex items-center flex-wrap gap-0">
              <div className="border border-dashed border-text-muted/25 px-2 py-1 shrink-0">
                <span className="font-mono text-[9px] text-text-muted uppercase tracking-widest">fan-in ↑</span>
              </div>
              <Arrow />
              <PNode label="Orchestrator" sub="merge results" />
              <Arrow />
              <PNode label="Trust Gate" sub="approval check" />
              <Arrow />
              <PNode label="Patch Commit" sub="git data api" />
              <Arrow />
              <PNode label="PR Comment" sub="github api" kind="output" />
            </div>

          </div>
        </div>

        <div className="max-w-7xl mx-auto px-6 py-6">
          <p className="font-mono text-xs text-text-muted">
            paths matching <span className="text-orange-400">auth · payment · billing · secret · admin</span> always route to human approval — never auto-patched.
          </p>
        </div>
      </section>

      {/* ── Built different ────────────────────────────────────────────── */}
      <section className="border-t border-bg-border">
        <div className="max-w-7xl mx-auto px-6 py-24">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-16">
            <h2 className="font-display font-black text-white leading-[0.9]" style={{ fontSize: 'clamp(2rem,4.5vw,4rem)' }}>built different.</h2>
            <p className="font-mono text-sm text-text-muted max-w-xs">every architectural decision was made with production reliability in mind.</p>
          </div>
          <div className="grid md:grid-cols-2 gap-px bg-bg-border">
            {features.map(({ n, title, body, tag }) => (
              <div key={n} className="group bg-bg-base p-8 md:p-10 flex flex-col gap-5 hover:bg-bg-surface transition-colors duration-200">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-text-muted">{n}</span>
                  <span className="badge">{tag}</span>
                </div>
                <h3 className="font-display font-bold text-white group-hover:text-orange-400 transition-colors duration-200 leading-tight" style={{ fontSize: 'clamp(1.2rem,2vw,1.6rem)' }}>
                  {title}
                </h3>
                <p className="font-mono text-sm text-text-secondary leading-relaxed flex-1">{body}</p>
                <div className="w-8 h-px bg-orange-500 opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pipeline steps strip ───────────────────────────────────────── */}
      <section className="border-t border-bg-border bg-bg-surface">
        <div className="max-w-7xl mx-auto px-6 py-24">
          <div className="mb-14">
            <p className="section-label mb-5">execution order</p>
            <h2 className="font-display font-black text-white leading-[0.92]" style={{ fontSize: 'clamp(1.75rem,3.5vw,3.25rem)' }}>
              from webhook to review comment<br />in under 5 seconds.
            </h2>
          </div>
          <div className="overflow-x-auto">
            <div className="flex items-stretch min-w-max">
              {pipelineSteps.map(({ n, label }, i) => (
                <div key={n} className="flex items-stretch">
                  <div className="group border border-bg-border bg-bg-base px-6 py-5 hover:border-orange-500/40 hover:bg-bg-raised transition-all duration-150 cursor-default flex flex-col gap-2 min-w-[120px]">
                    <span className="font-mono text-xs text-text-muted">{n}</span>
                    <span className="font-display font-semibold text-sm text-white group-hover:text-orange-400 transition-colors whitespace-nowrap">{label}</span>
                  </div>
                  {i < pipelineSteps.length - 1 && (
                    <div className="flex items-center px-1">
                      <span className="font-mono text-xs text-bg-border">›</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
          <p className="mt-6 font-mono text-xs text-text-muted">steps 04–06 run as parallel langgraph fan-outs · steps 01–03 and 07–08 are sequential</p>
        </div>
      </section>

      {/* ── Tech stack ────────────────────────────────────────────────── */}
      <section className="border-t border-bg-border">
        <div className="max-w-7xl mx-auto px-6 py-24">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-14">
            <p className="section-label">tech stack</p>
            <span className="font-mono text-xs text-text-muted">100% open source · no saas · no telemetry</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-bg-border">
            {techStack.map(([name, role]) => (
              <div key={name} className="group bg-bg-base px-6 py-5 hover:bg-bg-surface transition-colors duration-150 cursor-default">
                <div className="font-display font-bold text-lg text-white/25 group-hover:text-orange-400 transition-colors duration-200">{name}</div>
                <div className="font-mono text-xs text-text-muted mt-1.5">{role}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────────────────── */}
      <section className="border-t border-bg-border relative overflow-hidden">
        <div className="absolute inset-0 hero-bg opacity-60" />
        <div className="relative max-w-7xl mx-auto px-6 py-32">
          <p className="section-label mb-6">ready to ship better code?</p>
          <h2 className="font-display font-black text-white leading-[0.88] mb-10" style={{ fontSize: 'clamp(2.5rem,6vw,6rem)' }}>
            deploy sentinel<br />
            <span className="text-orange-500">in minutes.</span>
          </h2>
          <p className="font-mono text-sm text-text-muted mb-10 leading-relaxed max-w-md">
            one webhook. one environment variable. sentinel handles the rest —
            reviewing, testing, fixing, and learning from your codebase forever.
          </p>
          <div className="flex flex-wrap gap-4">
            <Link to="/docs" className="btn-primary" style={{ fontSize: '0.9375rem', padding: '0.875rem 2rem' }}>get started →</Link>
            <Link to="/agents" className="btn-secondary" style={{ fontSize: '0.9375rem', padding: '0.875rem 2rem' }}>meet the agents</Link>
          </div>
        </div>
      </section>

    </div>
  )
}
