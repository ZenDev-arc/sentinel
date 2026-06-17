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
  { id: 'docker-sandbox', label: 'docker sandbox' },
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
                'groq api key (free) — get one at console.groq.com',
                'huggingface token (free, optional) — used as automatic fallback in cascade mode',
                'github token or github app (for posting review comments)',
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
            <p className="text-text-muted text-sm mb-4 font-mono">
              install sentinel from pypi — no repo clone needed:
            </p>
            <CodeBlock
              language="bash"
              code={`pip install zendev-sentinel

# first-time setup wizard (saves api keys to ~/.sentinel/.env)
sentinel init`}
            />
            <p className="text-text-muted text-sm mt-6 mb-3 font-mono">build the docker sandbox image:</p>
            <CodeBlock
              language="bash"
              code="docker build -f docker/Dockerfile.sandbox -t sentinel-sandbox:latest ."
            />
            <p className="text-text-muted text-xs mt-4 text-text-muted font-mono">
              the sandbox image is built once and reused for every run. it has pytest, jest, and ts-jest pre-installed.
            </p>
          </section>

          {/* Configuration */}
          <section id="configuration" className="mb-14 scroll-mt-20">
            <h2 className="text-base font-semibold text-white mb-5 font-mono border-b border-bg-border pb-3">
              configuration
            </h2>
            <p className="text-text-muted text-sm mb-4 font-mono">
              <code className="text-orange-400">sentinel init</code> saves your keys to{' '}
              <code className="text-orange-400">~/.sentinel/.env</code> automatically.
              a local <code className="text-orange-400">.env</code> in your project directory overrides it.
            </p>
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
                    ['LLM_PROVIDER',          'cascade',       'cascade | groq | huggingface | ollama | anthropic'],
                    ['GROQ_API_KEY',           '—',             'free key from console.groq.com'],
                    ['HUGGINGFACE_API_KEY',    '—',             'free token — fallback in cascade mode'],
                    ['GITHUB_TOKEN',           '—',             'pat with repo scope (simple setup)'],
                    ['GITHUB_APP_ID',          '—',             'github app id (production setup)'],
                    ['GITHUB_WEBHOOK_SECRET',  '—',             'hmac-sha256 secret — auto-generated by github-setup'],
                    ['CHROMA_PERSIST_DIR',     './data/chroma', 'where the vector kb is stored on disk'],
                    ['SANDBOX_MEMORY_LIMIT',   '512m',          'docker container memory cap'],
                    ['RISK_HIGH_THRESHOLD',    '0.7',           '≥ this score triggers the full 19-agent pipeline'],
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
                  option a — automated wizard (recommended)
                </h3>
                <p className="text-text-muted text-xs font-mono mb-3 leading-relaxed">
                  run the wizard — it generates a webhook secret, walks you through github app creation step-by-step,
                  optionally starts an ngrok tunnel for local dev, and saves everything to ~/.sentinel/.env.
                </p>
                <CodeBlock language="bash" code="sentinel github-setup" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white mb-3 font-mono">
                  option b — personal access token (simplest)
                </h3>
                <div className="border border-bg-border divide-y divide-bg-border">
                  {[
                    'github → settings → developer settings → personal access tokens',
                    'generate token with repo scope',
                    'add GITHUB_TOKEN=ghp_... to ~/.sentinel/.env',
                    'manually add your webhook secret: GITHUB_WEBHOOK_SECRET=your-secret',
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
                  <div><span className="text-text-muted">secret        </span><span className="text-orange-400">matches GITHUB_WEBHOOK_SECRET in ~/.sentinel/.env</span></div>
                  <div><span className="text-text-muted">events        </span><span className="text-orange-400">pull requests  ·  push (optional)</span></div>
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
            <CodeBlock language="bash" code="sentinel run --repo owner/repo --pr 42" />
            <p className="text-text-muted text-sm mt-6 mb-3 font-mono">scan a local directory (no github pr needed):</p>
            <CodeBlock language="bash" code="sentinel scan --path ./myproject --all" />
            <p className="text-text-muted text-sm mt-6 mb-3 font-mono">start the webhook server (port 8000):</p>
            <CodeBlock language="bash" code="sentinel serve" />
            <p className="text-text-muted text-sm mt-6 mb-3 font-mono">run kb maintenance agents manually:</p>
            <CodeBlock language="bash" code="sentinel maintain" />
          </section>

          {/* Docker Sandbox */}
          <section id="docker-sandbox" className="mb-14 scroll-mt-20">
            <h2 className="text-base font-semibold text-white mb-5 font-mono border-b border-bg-border pb-3">
              docker sandbox
            </h2>

            <p className="text-text-secondary text-sm leading-relaxed mb-6 font-mono">
              the sandbox runs generated tests and bug reproduction inside an isolated docker container —
              no network access, non-root user, hard memory and cpu limits.
              without it, sentinel still reviews code but skips test execution, coverage analysis, and fix verification.
            </p>

            {/* What it does */}
            <h3 className="text-sm font-semibold text-white mb-3 font-mono">what the sandbox enables</h3>
            <div className="border border-bg-border divide-y divide-bg-border mb-8">
              {[
                ['test execution',      'runs pytest / jest against the pr code inside an isolated container'],
                ['coverage analysis',   'measures real line coverage, not estimated'],
                ['bug reproduction',    'executes failing code paths to confirm bugs are real, not false positives'],
                ['fix verification',    'applies proposed patches and re-runs tests to confirm they work'],
              ].map(([title, desc]) => (
                <div key={title} className="flex gap-4 px-4 py-3">
                  <span className="text-orange-400 text-xs font-mono shrink-0 mt-0.5 w-36">{title}</span>
                  <span className="text-text-secondary text-xs font-mono">{desc}</span>
                </div>
              ))}
            </div>

            {/* Prerequisites */}
            <h3 className="text-sm font-semibold text-white mb-3 font-mono">prerequisites</h3>
            <div className="border border-bg-border divide-y divide-bg-border mb-8">
              {[
                { step: '1', text: 'install docker desktop', link: 'https://www.docker.com/products/docker-desktop/', linkLabel: 'docker.com/products/docker-desktop' },
                { step: '2', text: 'start docker desktop and wait for "engine running" in the taskbar' },
                { step: '3', text: 'verify the cli is available: open a terminal and run docker --version' },
              ].map(({ step, text, link, linkLabel }) => (
                <div key={step} className="flex gap-4 px-4 py-3">
                  <span className="text-text-muted text-xs font-mono shrink-0">{step}.</span>
                  <span className="text-text-secondary text-xs font-mono">
                    {text}
                    {link && (
                      <> — <a href={link} target="_blank" rel="noopener noreferrer" className="text-orange-400 hover:underline">{linkLabel}</a></>
                    )}
                  </span>
                </div>
              ))}
            </div>

            {/* Build */}
            <h3 className="text-sm font-semibold text-white mb-3 font-mono">build the sandbox image</h3>
            <p className="text-text-muted text-xs font-mono mb-3">run once from the sentinel project root. takes ~2 minutes on first build, cached on subsequent runs.</p>
            <CodeBlock
              language="bash"
              code={`# clone the sentinel repo first (if you installed via pip, the docker/ dir is included)
git clone https://github.com/ZenDev-arc/sentinel.git
cd sentinel

# build the image
docker build -f docker/Dockerfile.sandbox -t sentinel-sandbox:latest .`}
            />
            <p className="text-text-muted text-xs font-mono mt-3 mb-8">
              the image includes python 3.12, pytest, pytest-cov, node 20, jest, ts-jest, and typescript.
              it intentionally has no network access at runtime.
            </p>

            {/* Verify */}
            <h3 className="text-sm font-semibold text-white mb-3 font-mono">verify the image</h3>
            <CodeBlock
              language="bash"
              code={`# should show sentinel-sandbox:latest
docker images sentinel-sandbox

# quick smoke test — runs pytest with no test files (exit code 5 = no tests found, that's correct)
docker run --rm --network none sentinel-sandbox:latest pytest --tb=no -q`}
            />
            <div className="border border-bg-border bg-bg-surface px-4 py-3 font-mono text-xs mt-3 mb-8">
              <span className="text-text-muted">expected output  </span>
              <span className="text-amber-400">no tests ran  ·  exit code 5</span>
              <span className="text-text-muted ml-4">→ sandbox is working correctly</span>
            </div>

            {/* Config */}
            <h3 className="text-sm font-semibold text-white mb-3 font-mono">sandbox configuration</h3>
            <div className="border border-bg-border overflow-x-auto mb-8">
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
                    ['SANDBOX_IMAGE',          'sentinel-sandbox:latest', 'docker image name — must match what you built'],
                    ['SANDBOX_MEMORY_LIMIT',   '512m',                   'container memory cap — increase for large test suites'],
                    ['SANDBOX_CPU_QUOTA',      '50000',                  'cpu quota (50000 = 50% of one core)'],
                    ['SANDBOX_TIMEOUT_SECONDS','120',                    'hard kill timeout for the container'],
                    ['DISABLE_SANDBOX',        'false',                  'set to true to skip sandbox entirely (cloud hosting)'],
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

            {/* Troubleshooting */}
            <h3 className="text-sm font-semibold text-white mb-3 font-mono">troubleshooting</h3>
            <div className="space-y-4">
              {[
                {
                  error: 'docker: command not found',
                  fix: 'docker desktop is installed but the cli is not in your path. open a new terminal session — docker desktop adds itself to path on first launch.',
                },
                {
                  error: 'cannot connect to docker daemon',
                  fix: 'docker desktop is not running. open it from your applications and wait for "engine running" in the taskbar icon before retrying.',
                },
                {
                  error: 'sentinel-sandbox:latest not found',
                  fix: 'the image has not been built yet. run: docker build -f docker/Dockerfile.sandbox -t sentinel-sandbox:latest .',
                },
                {
                  error: 'sandbox_run_done exit_code: 5',
                  fix: 'exit code 5 means pytest found no test files — this is expected on the first run if your repo has no tests yet. sentinel will generate tests on the next pr.',
                },
                {
                  error: 'sandbox_run_done exit_code: 2',
                  fix: 'exit code 2 means pytest had a collection error — usually an import error in the generated tests. sentinel will route these to the bug squad agents automatically.',
                },
              ].map(({ error, fix }) => (
                <div key={error} className="border border-bg-border">
                  <div className="px-4 py-2.5 bg-bg-surface border-b border-bg-border">
                    <code className="text-orange-400 text-xs">{error}</code>
                  </div>
                  <div className="px-4 py-2.5">
                    <p className="text-text-secondary text-xs font-mono leading-relaxed">{fix}</p>
                  </div>
                </div>
              ))}
            </div>
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
├── core/
│   ├── pipeline.py     langgraph graph definition
│   ├── sandbox.py      docker sandbox (python + jest/ts-jest)
│   ├── llm.py          provider factory (groq → huggingface cascade)
│   ├── project_utils.py  project-type detection (python / javascript / mixed)
│   ├── config.py       settings from ~/.sentinel/.env + local .env
│   └── state.py        pydantic state schema
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
