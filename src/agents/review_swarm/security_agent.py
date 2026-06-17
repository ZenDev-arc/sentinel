"""
Security Reviewer Agent

Scans the diff for:
  - Injection vulnerabilities (SQL, command, LDAP, XPath, template)
  - Authentication / authorization flaws
  - Hardcoded secrets, API keys, passwords
  - Unsafe deserialization
  - Cryptographic weaknesses (weak algorithms, insecure random, ECB mode)
  - SSRF, path traversal, open redirect
  - Missing input validation / output encoding
  - Insecure direct object references
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.core.state import (FindingCategory, FindingSeverity, PipelineState,
                            ReviewFinding)
from src.knowledge_base.models import KBEntryType
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

_SYSTEM = """You are SENTINEL's Security Review Agent — a senior AppSec engineer.

Analyse the provided git diff for security vulnerabilities.
Focus ONLY on code that was added or modified (lines starting with +).
Be THOROUGH — flag anything that could be a security risk, even if it's minor.
A finding is better than a missed vulnerability.

Return a JSON array of findings. Each finding:
{
  "title": "<concise vulnerability title>",
  "severity": "critical" | "high" | "medium" | "low" | "info",
  "file_path": "<file>",
  "line_start": <int or null>,
  "line_end": <int or null>,
  "description": "<what the vulnerability is and why it's dangerous>",
  "suggestion": "<specific fix with code example>"
}

Return [] ONLY if there are genuinely zero security concerns.
Do NOT wrap the JSON in markdown fences.

Security checklist — flag ALL of these:
Python/general:
- SQL/NoSQL injection (f-strings or % formatting in queries)
- Command injection (subprocess with shell=True, os.system, eval, exec)
- Hardcoded secrets (password=, api_key=, secret=, token= with literal values)
- Insecure deserialization (pickle.loads, yaml.load without Loader, marshal)
- Weak crypto (MD5/SHA1 for passwords, ECB mode, random for tokens)
- Missing auth checks on new API endpoints
- SSRF (requests/httpx/fetch to user-supplied URLs without allowlist)
- Path traversal (os.path.join or open() with user-controlled input)
- Mass assignment / missing input validation on user-controlled fields
- Prototype pollution, ReDoS (catastrophic backtracking in regexes)
- Missing rate limiting on auth endpoints
- Sensitive data in logs (log.info with password/token fields)
- JWT without expiry, weak JWT secret
- CORS misconfiguration (allow-origin: *)
- XSS (dangerouslySetInnerHTML, innerHTML with user data in JS/TS)
JavaScript/TypeScript specific:
- eval() or Function() constructor with user input
- dangerouslySetInnerHTML without sanitization
- localStorage storing sensitive tokens
- Missing CSRF protection
- Unvalidated redirects (window.location = userInput)
- npm packages imported without integrity check
- XSS (unescaped output in templates)
- CSRF (missing tokens on state-changing endpoints)
- Insecure redirect (redirect with user-supplied URL)
- Secrets in logs
"""


# Pre-scan for obvious hardcoded secrets before LLM call
_SECRET_PATTERN = re.compile(
    r'^\+.*\b(password|secret|api_key|apikey|private_key|access_token|auth_token)\s*=\s*["\'][^"\']{6,}["\']',
    re.IGNORECASE | re.MULTILINE,
)


def _prescan_secrets(diff: str) -> list[ReviewFinding]:
    findings = []
    for match in _SECRET_PATTERN.finditer(diff):
        findings.append(
            ReviewFinding(
                category=FindingCategory.SECURITY,
                severity=FindingSeverity.CRITICAL,
                file_path="(pre-scan)",
                title="Hardcoded secret detected",
                description=(
                    f"A hardcoded credential was detected in the diff: `{match.group(0)[:80]}…`. "
                    "Secrets must never be committed to source control."
                ),
                suggestion=(
                    "Remove the hardcoded value. Use environment variables or a secrets manager "
                    "(e.g., AWS Secrets Manager, HashiCorp Vault, .env loaded at runtime)."
                ),
            )
        )
    return findings


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _llm_review(diff: str, kb_context: str) -> list[dict]:
    llm = get_llm("strong")
    prompt = ""
    if kb_context:
        prompt += f"Relevant past security findings for this repo:\n{kb_context}\n\n"
    prompt += f"Diff to review:\n{diff[:6000]}"
    response = llm.invoke(
        [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def run(state: PipelineState, kb: KnowledgeBaseStore) -> dict:
    pr = state.pr
    log.info("security_agent_start", repo=pr.repo_full_name, pr=pr.pr_number)

    prescan = _prescan_secrets(pr.diff)

    kb_hits = kb.search(
        query=f"security vulnerability {pr.pr_title} {' '.join(pr.files_changed[:5])}",
        repo=pr.repo_full_name,
        n_results=3,
        entry_type=KBEntryType.REVIEW_OUTCOME,
    )
    kb_context = "\n".join(
        f"- {h.entry.title}: {h.entry.description[:120]}" for h in kb_hits
    )
    kb_hit_ids = [h.entry.id for h in kb_hits]

    try:
        raw = _llm_review(pr.diff, kb_context)
    except Exception as exc:
        log.warning("security_agent_llm_failed", error=str(exc))
        raw = []

    findings: list[ReviewFinding] = list(prescan)
    for item in raw:
        try:
            sev_str = item.get("severity", "medium").lower()
            sev = (
                FindingSeverity(sev_str)
                if sev_str in FindingSeverity._value2member_map_
                else FindingSeverity.MEDIUM
            )
            findings.append(
                ReviewFinding(
                    category=FindingCategory.SECURITY,
                    severity=sev,
                    file_path=item.get("file_path", ""),
                    line_start=item.get("line_start"),
                    line_end=item.get("line_end"),
                    title=item.get("title", "Security finding"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", ""),
                    kb_hit_ids=kb_hit_ids,
                )
            )
        except Exception as exc:
            log.warning("security_finding_parse_error", error=str(exc), item=item)

    for hit in kb_hits:
        kb.record_use(hit.entry.id)

    log.info("security_agent_done", count=len(findings))
    return {"security_findings": findings}
