"""
Centralised settings loaded from environment / .env file.
All secrets come exclusively from environment variables — never hardcoded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load global config first (~/.sentinel/.env), then local .env overrides it.
# This lets `pip install sentinel-ai` users configure once via `sentinel init`
# without needing a .env in every project directory.
_GLOBAL_ENV = Path.home() / ".sentinel" / ".env"
if _GLOBAL_ENV.exists():
    load_dotenv(_GLOBAL_ENV)
load_dotenv()  # local .env (if present) takes precedence over global

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────────────────────
    LLM_PROVIDER: str = "ollama"

    # Ollama (local, free — no API key)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_STRONG: str = "qwen2.5-coder:7b"
    OLLAMA_MODEL_FAST: str = "qwen2.5-coder:7b"

    # Groq (free API — https://console.groq.com)
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL_STRONG: str = "llama-3.3-70b-versatile"
    GROQ_MODEL_FAST: str = "llama-3.1-8b-instant"

    # Anthropic (paid — optional)
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_MODEL_STRONG: str = "claude-sonnet-4-6"
    LLM_MODEL_FAST: str = "claude-haiku-4-5-20251001"

    # Hugging Face Inference API (free — https://huggingface.co/settings/tokens)
    HUGGINGFACE_API_KEY: Optional[str] = None
    HF_MODEL_STRONG: str = "Qwen/Qwen2.5-72B-Instruct"
    HF_MODEL_FAST: str = "Qwen/Qwen2.5-7B-Instruct"

    # ── GitHub ────────────────────────────────────────────────────────────────
    GITHUB_APP_ID: Optional[str] = None
    GITHUB_APP_PRIVATE_KEY_PATH: str = "./keys/github-app.pem"
    # Set this directly to the PEM content (preferred on cloud hosts like Render/Railway
    # where you can't mount a file). Takes precedence over GITHUB_APP_PRIVATE_KEY_PATH.
    GITHUB_APP_PRIVATE_KEY: Optional[str] = None
    GITHUB_WEBHOOK_SECRET: str = ""
    GITHUB_TOKEN: Optional[str] = None

    # ── Chroma ────────────────────────────────────────────────────────────────
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION: str = "sentinel_kb"

    # ── API ───────────────────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_SECRET_KEY: str = "change-me"
    # Comma-separated list of allowed Host header values.
    # Set to your domain(s) in production, e.g. "sentinel.example.com,api.example.com"
    TRUSTED_HOSTS: str = "*"
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── Docker sandbox ────────────────────────────────────────────────────────
    SANDBOX_IMAGE: str = "sentinel-sandbox:latest"
    SANDBOX_TIMEOUT_SECONDS: int = 120
    SANDBOX_MEMORY_LIMIT: str = "512m"
    SANDBOX_CPU_PERIOD: int = 100000
    SANDBOX_CPU_QUOTA: int = 50000

    # ── Knowledge base ────────────────────────────────────────────────────────
    KB_CONFIDENCE_DECAY_DAYS: int = 30
    KB_CONFIDENCE_THRESHOLD: float = 0.3
    KB_CURATOR_REJECTION_THRESHOLD: int = 3
    KB_MAINTENANCE_CRON: str = "0 2 * * *"

    # ── Risk scoring ──────────────────────────────────────────────────────────
    RISK_HIGH_THRESHOLD: float = 0.7
    RISK_MEDIUM_THRESHOLD: float = 0.4
    RISK_SENSITIVE_PATTERNS: str = (
        "auth,payment,billing,secret,credential,password,token,admin,migrations"
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/sentinel.log"

    @field_validator("LLM_PROVIDER", mode="before")
    @classmethod
    def _check_provider(cls, v: str) -> str:
        allowed = {"ollama", "groq", "anthropic", "huggingface", "cascade"}
        if v.lower() not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {allowed}, got '{v}'")
        return v.lower()

    @property
    def sensitive_patterns(self) -> list[str]:
        return [p.strip() for p in self.RISK_SENSITIVE_PATTERNS.split(",") if p.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        return [h.strip() for h in self.TRUSTED_HOSTS.split(",") if h.strip()]

    @property
    def github_app_private_key(self) -> Optional[str]:
        # Env var takes precedence (cloud deployments where file mounts aren't available)
        if self.GITHUB_APP_PRIVATE_KEY:
            return self.GITHUB_APP_PRIVATE_KEY.replace("\\n", "\n")
        path = Path(self.GITHUB_APP_PRIVATE_KEY_PATH)
        if path.exists():
            return path.read_text()
        return None


settings = Settings()
