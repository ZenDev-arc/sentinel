# SENTINEL

**Self-healing AI code quality pipeline.**

SENTINEL reviews your code, finds bugs, proposes fixes, verifies them in an isolated sandbox, and auto-applies the safe ones — all without leaving your terminal.

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

## How it works

```
Your code
   │
   ▼
Risk assessment ──→ low risk: lightweight review
   │                high risk: full swarm
   ▼
Review swarm (parallel)
  ├── Architecture agent
  ├── Performance agent
  ├── Security agent
  └── Style & quality agent
   │
   ▼
Lead synthesis → findings report
   │
   ▼
Sandbox (Docker, no network, non-root)
  └── Run tests → find failures
   │
   ▼
Bug Squad (sequential)
  ├── Reproduce → isolate each failing test
  ├── Root cause → why it failed
  ├── Fix proposer → propose a patch
  └── Verifier → apply patch, re-run tests, confirm green
   │
   ▼
Approval gate
  ├── AUTO_MERGE  → safe fix, applied immediately
  └── HUMAN_REQUIRED → sensitive file or high risk
```

---

## Install

```bash
pip install sentinel-ai
```

Requires Python 3.11+ and Docker (for the sandbox).

---

## Setup

```bash
sentinel init
```

This walks you through getting two free API keys (takes ~2 minutes, no credit card):

- **Groq** — fast inference: [console.groq.com](https://console.groq.com)
- **HuggingFace** — fallback when Groq quota runs out: [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

SENTINEL uses both automatically (`cascade` mode) — Groq first, HuggingFace as a silent fallback.

---

## Usage

```bash
# Scan every file in a project
sentinel scan --path ./my-project --all

# Scan only your staged git changes
sentinel scan --path . --staged

# Scan changes vs a branch
sentinel scan --path . --branch main

# Save report to a file
sentinel scan --path . --all --output report.md

# Run on a GitHub PR (needs GITHUB_TOKEN in .env)
sentinel run --repo owner/repo --pr 42

# Start webhook server (auto-scans PRs on open)
sentinel serve
```

---

## Supported languages

| Language | Review | Sandbox tests | Auto-fix |
|---|---|---|---|
| Python | ✓ | ✓ (pytest) | ✓ |
| TypeScript / JavaScript | ✓ | coming soon | — |
| JSX / TSX | ✓ | coming soon | — |

---

## LLM providers

Set `LLM_PROVIDER` in `~/.sentinel/.env`:

| Provider | Cost | Setup |
|---|---|---|
| `cascade` | Free | Groq + HuggingFace keys (recommended) |
| `groq` | Free | Groq key only |
| `huggingface` | Free | HuggingFace token only |
| `ollama` | Free | Local GPU, no API key |
| `anthropic` | Paid | Anthropic API key |

---

## Security

- Sandbox runs with `network_mode=none`, non-root uid, memory + CPU limits
- Webhook payloads verified with HMAC-SHA256 before parsing
- Sensitive files (`auth`, `payment`, `migrations`, etc.) always require human approval
- All secrets in `~/.sentinel/.env` — never committed to version control

---

## Self-hosted (team use)

For teams, run SENTINEL on a shared server with [Ollama](https://ollama.com) — no API keys, no quota, unlimited scans:

```bash
ollama pull qwen2.5-coder:7b
LLM_PROVIDER=ollama sentinel serve
```

---

## License

[AGPL-3.0](LICENSE) — free to use and self-host. If you offer SENTINEL as a hosted service, your full stack must be open-sourced under the same license.
