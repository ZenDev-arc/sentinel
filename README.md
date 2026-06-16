<div align="center">

# SENTINEL

**Self-healing AI code review pipeline**

[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-orange?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-orange?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LLM](https://img.shields.io/badge/LLM-Groq%20%2B%20HuggingFace-orange?style=flat-square)](https://console.groq.com)
[![Docker](https://img.shields.io/badge/sandbox-Docker-orange?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![PyPI](https://img.shields.io/badge/pypi-zendev--sentinel-orange?style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/zendev-sentinel)

*19 agents. 5 swarms. Runs on every PR. Free.*

</div>

---

```
sentinel scan --path ./my-project --all
```

```
┌────────────────────────────────── Summary ──────────────────────────────────┐
│  Risk level        LOW  (0.25)                                              │
│  Files reviewed    2                                                        │
│  Findings          7                                                        │
│  Bugs found        3                                                        │
│  Auto-fixes        2    ← applied automatically                             │
│  Pending fixes     1    ← needs human review                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick start

```bash
pip install zendev-sentinel
sentinel init          # saves API keys to ~/.sentinel/.env
sentinel github-setup  # wires up your GitHub webhook
sentinel serve         # start listening for PRs
```

Two free API keys required — takes ~2 minutes, no credit card:

- **Groq** → [console.groq.com](https://console.groq.com)
- **HuggingFace** → [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

---

## What it does

<details>
<summary><b>🔍 Review swarm</b> — 5 agents fire in parallel on every PR</summary>

<br>

| Agent | Checks |
|---|---|
| **Security** | Injection, auth flaws, weak crypto, SSRF, XSS, eval(), hardcoded secrets |
| **Performance** | N+1 queries, unbounded queries, blocking async, O(n²), missing memoization |
| **Style** | Naming, bare excepts, mutable defaults, magic numbers, function length |
| **Architecture** | Layering violations, circular deps, god classes, tight coupling |
| **Lead reviewer** | De-duplicates and re-prioritises all findings by severity |

</details>

<details>
<summary><b>🧪 Test swarm</b> — writes and runs tests against your changes</summary>

<br>

- Generates unit tests per changed file (happy path + edge cases)
- Runs them in an isolated Docker sandbox — `network_mode=none`, non-root, memory-capped
- Parses coverage output and surfaces gaps below 80%
- Writes integration tests when multiple modules interact (medium/high risk only)

Supports **Python** (pytest) and **TypeScript / JavaScript** (jest + ts-jest).

</details>

<details>
<summary><b>🐛 Bug squad</b> — reproduces, traces, and fixes failures automatically</summary>

<br>

```
Failing test
    │
    ▼
Reproduce  →  strip to minimal repro script
    │
    ▼
Root cause  →  identify source file + line, form hypothesis
    │
    ▼
Fix proposer  →  draft 1–3 candidate patches (unified diff)
    │
    ▼
Verifier  →  apply each patch in sandbox, pick the first green one
    │
    ▼
AUTO_MERGE or HUMAN_REQUIRED
```

</details>

<details>
<summary><b>🧠 Self-healing knowledge base</b> — gets smarter with every review</summary>

<br>

ChromaDB + SBERT power a local vector store. Every finding and fix is stored and recalled on future PRs — so agents learn your codebase's patterns over time.

Four maintenance agents run on a schedule:

| Agent | Schedule | What it does |
|---|---|---|
| **Curator** | Nightly 02:00 UTC | Removes stale, reverted, and repeatedly-rejected entries |
| **Drift-checker** | Nightly 02:15 UTC | Archives entries whose code has since changed |
| **Consistency** | Weekly Sunday 03:00 UTC | Resolves contradictions between KB entries |
| **Consolidation** | Weekly Sunday 03:30 UTC | Merges near-duplicate entries into patterns |

No cloud. No data leaves your machine.

</details>

<details>
<summary><b>🔐 Trust layer</b> — every fix is explained and gated</summary>

<br>

- **Explainability agent** — attaches a plain-English rationale to every finding and fix
- **Approval gate** — classifies patches as `AUTO_MERGE` or `HUMAN_REQUIRED`

Files matching `auth`, `payment`, `billing`, `secret`, `credential`, `password`, `token`, `admin`, or `migrations` always route to `HUMAN_REQUIRED` — never auto-patched.

</details>

---

## Pipeline

```
PR opened / pushed
        │
        ▼
   Risk scorer  ──→  score 0.0–1.0
        │
    ┌───┴───────────────────────────────────────┐
    │ low risk          │ medium / high risk     │
    │ lightweight pass  │ full swarm             │
    └───────────────────┴───────────────────────┘
        │
        ▼
  ┌─────────────────────────────────────────────┐
  │  PARALLEL                                   │
  │  Review swarm      Test swarm               │
  │  ├── Security      ├── Module tests         │
  │  ├── Performance   ├── Coverage analysis    │
  │  ├── Style         └── Integration tests    │
  │  ├── Architecture                           │
  │  └── Lead reviewer                          │
  └─────────────────────────────────────────────┘
        │
        ▼  (on test failures)
  Bug squad  →  Reproduce → Root cause → Fix → Verify
        │
        ▼
  Trust layer  →  Explain → Gate → Post PR comment
```

---

## Commands

| Command | What it does |
|---|---|
| `sentinel init` | First-time setup wizard — saves keys to `~/.sentinel/.env` |
| `sentinel github-setup` | Generates webhook secret, walks through GitHub App creation |
| `sentinel scan --path . --all` | Scan a local directory (no PR needed) |
| `sentinel run --repo owner/repo --pr 42` | Run against a specific GitHub PR |
| `sentinel serve` | Start webhook server on port 8000 |
| `sentinel maintain` | Run KB maintenance agents manually |

<details>
<summary>More scan options</summary>

```bash
sentinel scan --path . --staged      # staged git changes only
sentinel scan --path . --branch main # diff vs a branch
sentinel scan --path . --all --output report.md  # save to file
```

</details>

---

## LLM providers

Set `LLM_PROVIDER` in `~/.sentinel/.env`:

| Provider | Cost | Notes |
|---|---|---|
| `cascade` | **Free** | Groq → HuggingFace fallback. Recommended. |
| `groq` | **Free** | Groq only |
| `huggingface` | **Free** | HuggingFace only |
| `ollama` | **Free** | Local GPU, no API key, no quota |
| `anthropic` | Paid | Highest quality |

---

## Supported languages

| Language | Review | Sandbox | Auto-fix |
|---|---|---|---|
| Python | ✓ | ✓ pytest | ✓ |
| TypeScript / JavaScript | ✓ | ✓ jest + ts-jest | ✓ |
| JSX / TSX | ✓ | ✓ jest + ts-jest | ✓ |

---

## Security

- Sandbox: `network_mode=none`, non-root uid 1000, memory + CPU hard limits
- Webhooks: HMAC-SHA256 verified before any payload is parsed
- Sensitive paths: auth / payment / migrations always require human approval
- Secrets: stored in `~/.sentinel/.env` — never committed to version control
- Pre-scan: regex secret detection on every diff before any LLM call

---

## Self-hosted (team use)

Run on a shared server with [Ollama](https://ollama.com) — no API keys, no quota:

```bash
ollama pull qwen2.5-coder:7b
LLM_PROVIDER=ollama sentinel serve
```

Or with Docker Compose:

```bash
docker compose -f docker/docker-compose.yml up -d
```

---

## License

[AGPL-3.0](LICENSE) — free to use and self-host. If you offer SENTINEL as a hosted service, your full stack must be open-sourced under the same license.
