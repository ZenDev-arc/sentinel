# Contributing to SENTINEL

Thanks for taking the time to contribute.

## Before you start

- Check [open issues](https://github.com/ZenDev-arc/sentinel/issues) to avoid duplicates.
- For large changes, open an issue first to discuss the approach.
- All contributions must be compatible with the [AGPL-3.0 license](LICENSE).

## Development setup

**Requirements:** Python 3.11+, Docker Desktop, Git

```bash
git clone https://github.com/ZenDev-arc/sentinel.git
cd sentinel

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e ".[dev]"

cp .env.example .env
# Fill in at minimum: GROQ_API_KEY, GITHUB_WEBHOOK_SECRET
```

Build the sandbox image (required for test-swarm and bug-squad tests):

```bash
docker build -f docker/Dockerfile.sandbox -t sentinel-sandbox:latest .
```

## Running tests

```bash
pytest                        # full test suite
pytest tests/unit/            # unit tests only (no Docker required)
pytest tests/integration/     # needs Docker + API keys in .env
```

## Project layout

```
src/
├── agents/
│   ├── review_swarm/     # security, performance, style, architecture, lead reviewer
│   ├── test_swarm/       # module tests, coverage, integration tests
│   ├── bug_squad/        # reproduction, root cause, fix proposer, verification
│   ├── trust_layer/      # explainability, approval gate, rollback
│   └── self_healing/     # curator, drift-checker, consistency, consolidation
├── core/
│   ├── pipeline.py       # LangGraph graph definition
│   ├── sandbox.py        # Docker sandbox runner
│   ├── llm.py            # LLM provider factory
│   └── config.py         # settings (pydantic-settings)
├── api/                  # FastAPI webhook + management API
├── integrations/         # GitHub API, Git utilities
└── knowledge_base/       # ChromaDB + sentence-transformers
frontend/                 # React docs site (Vite + Tailwind)
docker/                   # Dockerfiles and docker-compose
```

## Adding an agent

1. Create `src/agents/<swarm>/<name>_agent.py`
2. Implement a `run(state: PipelineState, kb: KnowledgeBaseStore) -> dict` function
3. Wire it into the LangGraph graph in `src/core/pipeline.py`
4. Add its log events to `src/core/logging.py` (`_EVENT_CONFIG`)
5. Write unit tests in `tests/unit/agents/`

## Pull request checklist

- [ ] Tests pass (`pytest`)
- [ ] No secrets or `.env` files committed
- [ ] Log events for new code paths added to `_EVENT_CONFIG` in `logging.py`
- [ ] `.env.example` updated if new env vars were added
- [ ] Docs updated if user-facing behaviour changed

## Code style

- Black + isort for formatting (run `black . && isort .` before committing)
- Type annotations on all public functions
- No comments explaining what the code does — only why (non-obvious constraints, workarounds)
- No hardcoded secrets anywhere

## Reporting security issues

**Do not open a public GitHub issue for security vulnerabilities.**
Email [devejya56@gmail.com](mailto:devejya56@gmail.com) with the details.
