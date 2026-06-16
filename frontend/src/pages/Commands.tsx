import CodeBlock from '../components/CodeBlock'

interface Command {
  name: string
  syntax: string
  desc: string
  flags?: { flag: string; desc: string }[]
  example: string
}

const commands: Command[] = [
  {
    name: 'init',
    syntax: 'sentinel init',
    desc: 'first-time setup wizard — asks for your groq api key and huggingface token and saves them to ~/.sentinel/.env. also checks that docker is running. run this once after installing.',
    example: 'sentinel init',
  },
  {
    name: 'github-setup',
    syntax: 'sentinel github-setup [OPTIONS]',
    desc: 'interactive wizard that guides you through creating a github app, generating a webhook secret, and optionally starting an ngrok tunnel so github can reach your local server. credentials are saved to ~/.sentinel/.env.',
    flags: [
      { flag: '--port INT', desc: 'port the server will listen on (default: 8000)' },
    ],
    example: 'sentinel github-setup --port 8000',
  },
  {
    name: 'serve',
    syntax: 'sentinel serve [OPTIONS]',
    desc: 'start the sentinel webhook server. listens for github pull_request events and runs the full pipeline automatically. prints auth mode and webhook url on startup. also launches the nightly kb maintenance scheduler.',
    flags: [
      { flag: '--host TEXT',      desc: 'bind address (default: 0.0.0.0)' },
      { flag: '--port INT',       desc: 'port number (default: 8000)' },
      { flag: '--repo-root PATH', desc: 'local repo path for drift-checker (default: .)' },
    ],
    example: 'sentinel serve --host 127.0.0.1 --port 9000',
  },
  {
    name: 'run',
    syntax: 'sentinel run --repo REPO --pr NUMBER',
    desc: 'run the full sentinel pipeline against a specific github pull request without starting the webhook server. useful for testing, ci integration, or re-running on an existing pr.',
    flags: [
      { flag: '--repo TEXT',     desc: 'repository in owner/repo format (required)' },
      { flag: '--pr INT',        desc: 'pull request number (required)' },
      { flag: '--force-review',  desc: 'skip risk-based routing — always run the full swarm' },
    ],
    example: 'sentinel run --repo acme/backend --pr 142',
  },
  {
    name: 'scan',
    syntax: 'sentinel scan [OPTIONS]',
    desc: 'scan local code for bugs and code quality issues — no github pr or webhook required. reads your local files or git diff and runs the full sentinel pipeline, printing the report to your terminal.',
    flags: [
      { flag: '--path PATH',     desc: 'directory to scan (default: current dir)' },
      { flag: '--all',           desc: 'scan every source file in the path, ignoring git diff' },
      { flag: '--staged',        desc: 'scan only staged git changes (git diff --cached)' },
      { flag: '--branch BRANCH', desc: 'diff against a branch, e.g. main' },
      { flag: '--force-review',  desc: 'always run full review swarm regardless of risk score' },
      { flag: '--output FILE',   desc: 'save the report to a markdown file' },
    ],
    example: 'sentinel scan --path ./myproject --all --output report.md',
  },
  {
    name: 'maintain',
    syntax: 'sentinel maintain [OPTIONS]',
    desc: 'run all four self-healing kb maintenance agents (curator, drift-checker, consistency, consolidation) once immediately. useful before first production deployment or after importing external data.',
    flags: [
      { flag: '--repo-root PATH', desc: 'path to repo for drift-checker (default: .)' },
    ],
    example: 'sentinel maintain --repo-root /opt/repos/backend',
  },
]

const envCommands = [
  {
    label: 'install sentinel (recommended — no repo clone needed)',
    code: 'pip install zendev-sentinel\nsentinel init',
  },
  {
    label: 'cascade mode — groq primary, huggingface fallback (default after init)',
    code: '# both keys are free — sentinel switches automatically when groq quota runs out\nLLM_PROVIDER=cascade\nGROQ_API_KEY=gsk_...\nHUGGINGFACE_API_KEY=hf_...',
  },
  {
    label: 'option b — groq only (free, fast)',
    code: '# add to ~/.sentinel/.env or local .env\nLLM_PROVIDER=groq\nGROQ_API_KEY=gsk_...',
  },
  {
    label: 'option c — ollama (local, no api key, needs gpu)',
    code: 'ollama serve\nollama pull qwen2.5-coder:7b\n# then set in ~/.sentinel/.env:\nLLM_PROVIDER=ollama',
  },
  {
    label: 'build the docker sandbox image',
    code: 'docker build -f docker/Dockerfile.sandbox \\\n  --build-arg REQUIREMENTS_FILE=requirements.txt \\\n  -t sentinel-sandbox:latest .',
  },
  {
    label: 'run tests',
    code: 'pytest tests/ -v --tb=short',
  },
  {
    label: 'check kb health via api',
    code: 'curl http://localhost:8000/api/kb/stats | python -m json.tool',
  },
  {
    label: 'trigger pipeline via api',
    code: `curl -X POST http://localhost:8000/api/pipeline/trigger \\
  -H "Content-Type: application/json" \\
  -d '{"repo": "owner/repo", "pr_number": 42}'`,
  },
]

export default function Commands() {
  return (
    <div className="max-w-4xl mx-auto px-6 py-12">

      {/* Header */}
      <div className="mb-12">
        <p className="section-label mb-3">reference</p>
        <h1 className="font-display font-black text-white mb-3" style={{ fontSize: 'clamp(2rem,3.5vw,3rem)' }}>commands</h1>
        <p className="text-text-muted text-sm font-mono">
          sentinel ships a <code className="text-orange-400">sentinel</code> cli with six subcommands.
          after <code className="text-orange-400">pip install zendev-sentinel</code> it is available everywhere on your system.
        </p>
      </div>

      {/* CLI Commands */}
      <div className="space-y-10 mb-16">
        {commands.map(cmd => (
          <div key={cmd.name} className="border border-bg-border">
            {/* Command header */}
            <div className="flex items-start gap-4 px-5 py-4 border-b border-bg-border bg-bg-surface">
              <code className="text-orange-400 font-mono font-semibold text-sm shrink-0">{cmd.name}</code>
              <p className="text-text-muted text-xs font-mono leading-relaxed">{cmd.desc}</p>
            </div>

            <div className="p-5 space-y-5">
              <CodeBlock language="bash" code={cmd.syntax} />

              {cmd.flags && (
                <div>
                  <p className="section-label mb-3">flags</p>
                  <div className="border border-bg-border divide-y divide-bg-border">
                    {cmd.flags.map(f => (
                      <div key={f.flag} className="flex gap-6 px-4 py-2.5">
                        <code className="text-amber-400 font-mono text-xs shrink-0 w-44">{f.flag}</code>
                        <span className="text-text-muted text-xs font-mono">{f.desc}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <p className="section-label mb-3">example</p>
                <CodeBlock language="bash" code={cmd.example} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Utility commands */}
      <div className="mb-16">
        <p className="section-label mb-6">useful shell commands</p>
        <div className="space-y-6">
          {envCommands.map(({ label, code }) => (
            <div key={label}>
              <p className="text-sm text-text-secondary font-mono mb-3">{label}</p>
              <CodeBlock language="bash" code={code} />
            </div>
          ))}
        </div>
      </div>

      {/* API endpoints */}
      <div>
        <p className="section-label mb-6">management api endpoints</p>
        <div className="border border-bg-border overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-bg-border bg-bg-surface">
                <th className="text-left px-4 py-2.5 text-text-muted font-medium">method</th>
                <th className="text-left px-4 py-2.5 text-text-muted font-medium">path</th>
                <th className="text-left px-4 py-2.5 text-text-muted font-medium">description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-bg-border">
              {[
                ['GET',  '/health',                      'server health check'],
                ['GET',  '/api/status',                  'system health + auth mode'],
                ['GET',  '/api/runs',                    'recent pipeline runs'],
                ['GET',  '/api/runs/{id}',               'single run detail'],
                ['GET',  '/api/kb/stats',                'knowledge base health'],
                ['GET',  '/api/approvals',               'pending human fixes'],
                ['POST', '/api/approvals/{id}/approve',  'approve a fix'],
                ['POST', '/api/approvals/{id}/reject',   'reject a fix'],
                ['GET',  '/api/agents/status',           'maintenance agent status'],
                ['POST', '/api/maintenance/trigger',     'trigger maintenance now'],
                ['POST', '/api/pipeline/trigger',        'run pipeline on a pr'],
                ['POST', '/webhook/github',              'github webhook receiver'],
              ].map(([method, path, desc]) => (
                <tr key={path} className="hover:bg-bg-surface transition-colors">
                  <td className={`px-4 py-2.5 font-semibold ${method === 'GET' ? 'text-white' : 'text-amber-400'}`}>
                    {method}
                  </td>
                  <td className="px-4 py-2.5 text-orange-400">{path}</td>
                  <td className="px-4 py-2.5 text-text-muted">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  )
}
