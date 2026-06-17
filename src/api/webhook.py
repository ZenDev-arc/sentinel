"""
FastAPI Webhook Server

Receives GitHub webhook events (pull_request, push) and kicks off the
SENTINEL pipeline asynchronously.

Security:
  - HMAC-SHA256 webhook signature verified on every request before processing
  - Rate limiting via slowapi (default: 60 req/min per IP)
  - Request body limited to 10 MB
  - Only processes pull_request events with actions: opened, synchronize, reopened
  - No raw payload stored in logs (only PR metadata)
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import (BackgroundTasks, FastAPI, HTTPException, Request,
                     Response, status)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.management import router as management_router
from src.core.config import settings
from src.core.logging import configure_logging, get_logger
from src.integrations.git_utils import fetch_pr_diff, fetch_pr_files
from src.integrations.github_client import (GitHubClient, build_from_webhook,
                                            verify_webhook_signature)

log = get_logger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("sentinel_api_startup", port=settings.API_PORT)
    yield
    log.info("sentinel_api_shutdown")


app = FastAPI(
    title="SENTINEL",
    description="Self-healing multi-agent code quality pipeline",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,  # disable Swagger UI in production
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_hosts,
)

# CORS — allow the frontend dev server and any deployed frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Management API
app.include_router(management_router)

# Serve built frontend from /frontend/dist (production).
# Mounted at /app/ so API and webhook routes at / are never shadowed.
from pathlib import Path as _Path

_frontend_dist = _Path(__file__).parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount(
        "/app", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend"
    )

_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook/github")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def github_webhook(
    request: Request, background_tasks: BackgroundTasks
) -> Response:
    # Body size guard
    try:
        content_length = int(request.headers.get("content-length", "0"))
    except ValueError:
        content_length = 0
    if content_length > _MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")

    body = await request.body()

    # ── Signature verification (MUST happen before any parsing) ──────────────
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_webhook_signature(body, sig):
        log.warning("webhook_signature_invalid", remote=get_remote_address(request))
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    delivery = request.headers.get("X-GitHub-Delivery", "")

    try:
        import json

        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    log.info("webhook_received", gh_event=event, delivery=delivery)

    if event == "ping":
        log.info("webhook_ping_ok", hook=payload.get("hook", {}).get("id"))
        return Response(status_code=status.HTTP_200_OK)

    if event == "pull_request":
        action = payload.get("action", "")
        if action in ("opened", "synchronize", "reopened"):
            background_tasks.add_task(_handle_pull_request, payload)
        else:
            log.info("webhook_pr_action_ignored", action=action)

    elif event == "push":
        # Record pushed commits for the drift checker / curator
        background_tasks.add_task(_handle_push, payload)

    return Response(status_code=status.HTTP_202_ACCEPTED)


# ── Background handlers ───────────────────────────────────────────────────────


async def _handle_pull_request(payload: dict) -> None:
    """Full SENTINEL pipeline triggered by a PR event."""
    from src.core.pipeline import compile_pipeline
    from src.core.state import PipelineState, PRMetadata

    pr_data = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})
    installation_data = payload.get("installation", {})

    repo_full_name = repo_data.get("full_name", "")
    pr_number = pr_data.get("number", 0)
    installation_id = installation_data.get("id")

    log.info("pipeline_start", repo=repo_full_name, pr=pr_number)

    try:
        gh = build_from_webhook(payload)
        diff = await asyncio.to_thread(fetch_pr_diff, repo_full_name, pr_number)
        files = await asyncio.to_thread(fetch_pr_files, repo_full_name, pr_number)

        pr_meta = PRMetadata(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            pr_title=pr_data.get("title", ""),
            pr_body=pr_data.get("body", "") or "",
            base_branch=pr_data.get("base", {}).get("ref", ""),
            head_branch=pr_data.get("head", {}).get("ref", ""),
            head_sha=pr_data.get("head", {}).get("sha", ""),
            author=pr_data.get("user", {}).get("login", ""),
            files_changed=files,
            diff=diff,
            additions=pr_data.get("additions", 0),
            deletions=pr_data.get("deletions", 0),
            installation_id=installation_id,
        )

        initial_state = PipelineState(pr=pr_meta)
        pipeline = compile_pipeline()

        final_state_raw = await asyncio.to_thread(pipeline.invoke, initial_state)
        # LangGraph returns a plain dict; reconstruct the typed state object.
        if isinstance(final_state_raw, dict):
            final_state = PipelineState.model_validate(final_state_raw)
        else:
            final_state = final_state_raw

        # Auto-commit approved fixes
        for fix in final_state.auto_applied_fixes:
            commit_sha = await asyncio.to_thread(
                gh.commit_fix,
                repo_full_name,
                fix,
                pr_meta.head_branch,
                f"[SENTINEL] {fix.description}\n\n{fix.rationale}",
            )
            if commit_sha:
                fix.applied = True
                fix.commit_sha = commit_sha

        # Post consolidated report to PR
        if final_state.pr_comment:
            await asyncio.to_thread(
                gh.post_pr_comment,
                repo_full_name,
                pr_number,
                final_state.pr_comment,
            )

        # Post human-required fixes as suggestions
        for fix in final_state.pending_human_fixes:
            await asyncio.to_thread(
                gh.create_pr_suggestion,
                repo_full_name,
                pr_number,
                fix,
                pr_meta.head_sha,
            )

        log.info(
            "pipeline_done",
            repo=repo_full_name,
            pr=pr_number,
            run_id=final_state.run_id,
        )

        # Persist run summary and pending approvals so the dashboard can display them
        from datetime import datetime as _dt

        from src.api.store import save_approval, save_run

        save_run(
            {
                "run_id": final_state.run_id,
                "repo": repo_full_name,
                "pr": pr_number,
                "started_at": final_state.started_at.isoformat(),
                "completed_at": _dt.utcnow().isoformat(),
                "status": final_state.status.value,
                "findings": len(final_state.consolidated_findings),
                "tests_generated": len(final_state.generated_tests),
                "bugs_found": len(final_state.bug_reports),
                "auto_fixes": len(final_state.auto_applied_fixes),
                "pending_fixes": len(final_state.pending_human_fixes),
                "risk_level": (
                    final_state.risk.level.value if final_state.risk else None
                ),
                "risk_score": final_state.risk.score if final_state.risk else None,
            }
        )
        for fix in final_state.pending_human_fixes:
            save_approval(
                {
                    "id": fix.id,
                    "repo": repo_full_name,
                    "pr": pr_number,
                    "description": fix.description,
                    "rationale": fix.rationale,
                    "patch": fix.patch,
                    "affected_files": fix.affected_files,
                    "classification": fix.classification.value,
                    "run_id": final_state.run_id,
                }
            )

    except Exception as exc:
        log.error("pipeline_failed", repo=repo_full_name, pr=pr_number, error=str(exc))
        from datetime import datetime as _dt

        from src.api.store import save_run

        save_run(
            {
                "repo": repo_full_name,
                "pr": pr_number,
                "started_at": _dt.utcnow().isoformat(),
                "completed_at": _dt.utcnow().isoformat(),
                "status": "failed",
                "error": str(exc),
            }
        )


async def _handle_push(payload: dict) -> None:
    """Record pushed commits — used by the Curator to detect reverts."""
    from src.api.store import record_revert

    commits = payload.get("commits", [])
    revert_shas = [c["id"] for c in commits if "revert" in c.get("message", "").lower()]
    if revert_shas:
        log.info("revert_commits_detected", shas=revert_shas)
        for sha in revert_shas:
            record_revert(sha)
