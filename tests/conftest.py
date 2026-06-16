"""
Shared pytest configuration and fixtures.
Sets test environment variables before any module-level imports.
"""

import os

import pytest

# Override settings for test environment
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")
os.environ.setdefault("GITHUB_TOKEN", "ghp_test")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("CHROMA_PERSIST_DIR", "/tmp/sentinel_test_chroma")
os.environ.setdefault("LOG_LEVEL", "WARNING")


@pytest.fixture(autouse=True)
def reset_lru_caches():
    """Clear LRU-cached singletons between tests."""
    from src.core.llm import get_llm
    get_llm.cache_clear()
    yield
    get_llm.cache_clear()
