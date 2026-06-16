import { useState } from 'react'
import CodeBlock from '../components/CodeBlock'
import clsx from 'clsx'

const sections = [
  { id: 'overview',       label: 'overview' },
  { id: 'requirements',   label: 'requirements' },
  { id: 'installation',   label: 'installation' },
  { id: 'configuration',  label: 'configuration' },
  { id: 'github-setup',   label: 'github setup' },
  { id: 'first-run',      label: 'first run' },
  { id: 'production',     label: 'production (docker)' },
  { id: 'architecture',   label: 'architecture' },
]

export default function Docs() {
  const [active, setActive] = useState('overview')

  const scrollTo = (id: string) => {
    setActive(id)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-16">
      <div className="flex gap-12">

        {/* Sidebar */}
        <aside className="hidden lg:block w-44 shrink-0">
          <div className="sticky top-20">
            <p className="section-label mb-4">on this page</p>
            <nav className="flex flex-col gap-0.5">
              {sections.map(s => (
                <button
                  key={s.id}
                  onClick={() => scrollTo(s.id)}
                  className={clsx(
                    'text-left px-3 py-1.5 text-xs font-mono transition-all duration-150 border-l-2',
                    active === s.id
                      ? 'border-orange-500 text-orange-400'
                      : 'border-transparent text-text-muted hover:text-text-secondary hover:border-bg-hover'
                  )}
                >
                  {s.label}
                </button>
              ))}
            </nav>
          </div>
        </aside>

        {/* Content */}
        <article className="flex-1 min-w-0">

          <h1 className="font-display font-black text-white mb-3" style={{ fontSize: 'clamp(2rem,3.5vw,3rem)' }}>documentation</h1>
          <p className="text-text-muted text-sm font-mono mb-12">everything you need to run sentinel on your repository.</p>

          {/* Overview */}
          <section id="overview" className="mb-14 scroll-mt-20">
            <h2 className="text-base font-semibold text-white mb-5 font-mono border-b border-bg-border pb-3">
              overview
            </h2>
            <p className="text-text-secondary text-sm leading-relaxed mb-6 font-mono">
              sentinel is a multi-agent ai pipeline that plugs into your github repository via a webhook.
              it fires on every pull request and runs up to 19 specialized agents — in parallel where possible,
              sequentially where dependencies require it — to produce a single consolidated review comment,
              auto-fix low-risk issues, and build a self-healing knowledge base about your codebase.
            </p>
            <div className="grid sm:grid-cols-3 gap-px bg-bg-border">
              {[
                { label: 'agents',  value: '19' },
                { label: 'swarms',  value: '5' },
                { label: 'loc',     value: '~5k' },
              ].map(({ label, value }) => (
                <div key={label} className="bg-bg-base px-5 py-4">
                  <div className="text-2xl font-bold text-orange-400 font-mono">{value}</div>
                  <div className="text-xs text-text-muted font-mono mt-1">{label}</div>
                </div>
              ))}
            </div>
          </section>

          {/* Requirements */}
          <section id="requirements" className="mb-14 scroll-mt-20">
            <h2 className="text-base font-semibold text-white mb-5 font-mono border-b border-bg-border pb-3">
              requirements
            </h2>
            <div className="border border-bg-border divide-y divide-bg-border">
              {[
                'python 3.11 or 3.12',
                'docker desktop (for sandbox execution)',
                'llm: anthropic api key  OR  ollama running locally',
                'github token (personal access token or github app)',
                '~2 gb disk for chroma + sbert model (downloaded on first run)',
              ].map(req => (
                <div key={req} className="flex items-start gap-3 px-4 py-3">
                  <span className="text-orange-400 text-xs mt-0.5 shrink-0">✓</span>
                  <span className="font-mono text-sm text-text-secondary">{req}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Installation */}
          <section id="installation" className="mb-14 scroll-mt-20">
            <h2 className="text-base font-semibold text-white mb-5 font-mono border-b border-bg-border pb-3">
              installation
            </h2>
            <p className="text-text-muted text-sm mb-4 font-mono">clone the repo and install python dependencies:</p>
            <CodeBlock
              language="bash"
              code={`git clone https://github.com/your-org/sentinel.git
cd sentinel

# create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # linux / macos
.venv\\Scripts\\activate.bat      # windows

# install all dependencies
pip install -r requirements.txt`}
            />
            <p className="text-text-muted text-sm mt-6 mb-3 font-mono">build the docker sandbox image:</p>
            <CodeBlock
              language="bash"
              code="docker build -f docker/Dockerfile.sandbox -t sentinel-sandbox:latest ."
            />
          </section>

          {/* Configuration */}
          <section id="configuration" className="mb-14 scroll-mt-20">
            <h2 className="text-base font-semibold text-white mb-5 font-mono border-b border-bg-border pb-3">
              configuration
            </h2>
            <p className="text-text-muted text-sm mb-4 font-mono">
              copy the example env file and fill in your values. all secrets live in{' '}
              <code className="text-orange-400">.env</code> — never commit it.
            </p>
            <CodeBlock language="bash" code="cp .env.example .env" />
            <p className="text-text-muted text-sm mt-6 mb-4 font-mono">key settings:</p>
            <div className="border border-bg-border overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-bg-border bg-bg-surface">
                    <th className="text-left px-4 py-2.5 text-text-muted font-medium">variable</th>
                    <th className="text-left px-4 py-2.5 text-text-muted font-medium">default</th>
                    <th className="text-left px-4 py-2.5 text-text-muted font-medium">description</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-bg-border">
                  {[
                    ['LLM_PROVIDER',         'anthropic',     'anthropic or ollama'],
                    ['ANTHROPIC_API_KEY',     '—',             'required if using claude'],
                    ['OLLAMA_MODEL',          'llama3.1:8b',   'any model served by ollama'],
                    ['GITHUB_TOKEN',          '—',             'pat with repo scope'],
                    ['GITHUB_WEBHOOK_SECRET', '—',             'secret for hmac verification'],
                    ['CHROMA_PERSIST_DIR',    './data/chroma', 'where the kb is stored on disk'],
                    ['SANDBOX_MEMORY_LIMIT',  '512m',          'docker container memory cap'],
                    ['RISK_HIGH_THRESHOLD',   '0.7',           '≥ this score triggers full pipeline'],
                  ].map(([k, d, desc]) => (
                    <tr key={k} className="hover:bg-bg-surface transition-colors">
                      <td className="px-4 py-2.5 text-orange-400">{k}</td>
                      <td className="px-4 py-2.5 text-amber-400">{d}</td>
                      <td className="px-4 py-2.5 text-text-muted">{desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* GitHub Setup */}
          <section id="github-setup" className="mb-14 scroll-mt-20">
            <h2 className="text-base font-semibold text-white mb-5 font-mono border-b border-bg-border pb-3">
              github setup
            </h2>
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold text-white mb-3 font-mono">
                  option a — personal access token (simplest)
                </h3>
                <div className="border border-bg-border divide-y divide-bg-border">
                  {[
                    'go to github → settings → developer settings → personal access tokens',
                    'generate token with repo scope',
                    'set GITHUB_TOKEN=ghp_... in your .env',
                  ].map((step, i) => (
                    <div key={i} className="flex gap-4 px-4 py-3">
                      <span className="text-text-muted text-xs font-mono shrink-0">{i + 1}.</span>
                      <span className="text-text-secondary text-xs font-mono">{step}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white mb-3 font-mono">webhook configuration</h3>
                <div className="border border-bg-border bg-bg-surface px-4 py-4 font-mono text-xs space-y-2">
                  <div><span className="text-text-muted">payload url   </span><span className="text-white">https://your-server.com/webhook/github</span></div>
                  <div><span className="text-text-muted">content type  </span><span className="text-amber-400">application/json</span></div>
                  <div><span className="text-text-muted">secret        </span><span className="text-orange-400">matches GITHUB_WEBHOOK_SECRET in .env</span></div>
                  <div><span className="text-text-muted">events        </span><span className="text-orange-400">pull requests</span></div>
                </div>
              </div>
            </div>
          </section>

          {/* First run */}
          <section id="first-run" className="mb-14 scroll-mt-20">
            <h2 className="text-base font-semibold text-white mb-5 font-mono border-b border-bg-border pb-3">
              first run
            </h2>
            <p className="text-text-muted text-sm mb-4 font-mono">test against a real pr without starting the webhook server:</p>
            <CodeBlock language="bash" code="python main.py run --repo owner/repo --pr 42" />
            <p className="text-text-muted text-sm mt-6 mb-3 font-mono">start the webhook server (port 8000):</p>
            <CodeBlock language="bash" code="python main.py serve" />
            <p className="text-text-muted text-sm mt-6 mb-3 font-mono">run kb maintenance agents manually:</p>
            <CodeBlock language="bash" code="python main.py maintain" />
          </section>

          {/* Production */}
          <section id="production" className="mb-14 scroll-mt-20">
            <h2 className="text-base font-semibold text-white mb-5 font-mono border-b border-bg-border pb-3">
              production (docker compose)
            </h2>
            <p className="text-text-muted text-sm mb-4 font-mono">
              runs sentinel + chroma in docker. fill in your <code className="text-orange-400">.env</code> first.
            </p>
            <CodeBlock
              language="bash"
              code={`# build and start all services
docker compose -f docker/docker-compose.yml up -d

# view logs
docker compose -f docker/docker-compose.yml logs -f sentinel

# stop
docker compose -f docker/docker-compose.yml down`}
            />
          </section>

          {/* Architecture */}
          <section id="architecture" className="mb-14 scroll-mt-20">
            <h2 className="text-base font-semibold text-white mb-5 font-mono border-b border-bg-border pb-3">
              architecture
            </h2>
            <div className="border border-bg-border bg-bg-surface px-5 py-5 font-mono text-xs leading-relaxed text-text-secondary overflow-x-auto">
              <pre>{`src/
├── core/           state schema · llm factory · langgraph pipeline · docker sandbox
├── agents/
│   ├── risk_scorer.py
│   ├── review_swarm/   security · performance · style · architecture · lead reviewer
│   ├── test_swarm/     module tests · coverage analysis · integration tests
│   ├── bug_squad/      reproduction · root-cause · fix-proposer · verification
│   ├── trust_layer/    explainability · approval gate
│   ├── self_healing/   curator · drift-checker · consistency · consolidation
│   └── orchestrator.py
├── knowledge_base/ chroma store + sbert embedder
├── integrations/   github api · git utilities
├── api/            fastapi webhook server + management api
└── scheduler/      apscheduler for nightly/weekly kb maintenance`}</pre>
            </div>
          </section>

        </article>
      </div>
    </div>
  )
}
