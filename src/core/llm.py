"""
LLM factory — returns a LangChain chat model regardless of provider.

Providers (set LLM_PROVIDER in .env):
  - cascade      Groq primary → HuggingFace fallback (recommended: maximises free quota)
  - groq         free API, fast — get a key at https://console.groq.com
  - huggingface  free serverless inference — get a token at https://huggingface.co/settings/tokens
  - ollama       local, free, no API key — needs Ollama installed
  - anthropic    paid API — only if you need Claude specifically

Usage:
    llm = get_llm("strong")   # security, root-cause, fix proposals
    llm = get_llm("fast")     # style, explanation, aggregation
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from src.core.config import settings

# Singleton callback — stateless, reads ContextVar at fire time
_TOKEN_CB = None


def _get_token_cb():
    global _TOKEN_CB
    if _TOKEN_CB is None:
        from src.core.token_tracker import SentinelTokenCallback

        _TOKEN_CB = SentinelTokenCallback()
    return _TOKEN_CB


def get_llm(tier: str = "fast") -> BaseChatModel:
    """Return a chat model for the requested tier with token tracking attached."""
    provider = settings.LLM_PROVIDER

    if provider == "ollama":
        model = _ollama_model(tier)
    elif provider == "groq":
        model = _groq_model(tier)
    elif provider == "anthropic":
        model = _anthropic_model(tier)
    elif provider == "huggingface":
        model = _huggingface_model(tier)
    elif provider == "cascade":
        model = _cascade_model(tier)
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{provider}'. "
            "Choose 'cascade', 'groq', 'huggingface', 'ollama', or 'anthropic'."
        )

    # Inject token-tracking callback (no-op when no tracker is active).
    # cascade returns RunnableWithFallbacks which doesn't support .callbacks —
    # for that case the callback is already injected into the underlying models
    # inside _cascade_model(), so we skip injection here.
    if provider != "cascade":
        cb = _get_token_cb()
        existing = list(getattr(model, "callbacks", None) or [])
        if not any(type(c) is type(cb) for c in existing):
            model.callbacks = existing + [cb]
    return model


def _ollama_model(tier: str) -> BaseChatModel:
    try:
        from langchain_ollama import ChatOllama
    except ImportError as e:
        raise ImportError("Run: pip install langchain-ollama") from e

    model = (
        settings.OLLAMA_MODEL_STRONG if tier == "strong" else settings.OLLAMA_MODEL_FAST
    )
    return ChatOllama(
        model=model,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0,
    )


def _groq_model(tier: str) -> BaseChatModel:
    try:
        from langchain_groq import ChatGroq
    except ImportError as e:
        raise ImportError("Run: pip install langchain-groq") from e

    if not settings.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set. "
            "Get a free key at https://console.groq.com, then add it to .env."
        )

    model = settings.GROQ_MODEL_STRONG if tier == "strong" else settings.GROQ_MODEL_FAST
    return ChatGroq(
        model=model,
        api_key=settings.GROQ_API_KEY,
        temperature=0,
        request_timeout=30,
    )


def _anthropic_model(tier: str) -> BaseChatModel:
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as e:
        raise ImportError("Run: pip install langchain-anthropic anthropic") from e

    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Either set LLM_PROVIDER=ollama or LLM_PROVIDER=groq for a free option."
        )

    model_id = (
        settings.LLM_MODEL_STRONG if tier == "strong" else settings.LLM_MODEL_FAST
    )
    return ChatAnthropic(
        model=model_id,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=4096,
        temperature=0,
    )


def _huggingface_model(tier: str) -> BaseChatModel:
    try:
        from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
    except ImportError as e:
        raise ImportError(
            "Run: pip install langchain-huggingface huggingface_hub"
        ) from e

    if not settings.HUGGINGFACE_API_KEY:
        raise RuntimeError(
            "HUGGINGFACE_API_KEY is not set. "
            "Get a free token at https://huggingface.co/settings/tokens "
            "(Read permission is enough), then add it to .env."
        )

    model = settings.HF_MODEL_STRONG if tier == "strong" else settings.HF_MODEL_FAST
    endpoint = HuggingFaceEndpoint(
        repo_id=model,
        huggingfacehub_api_token=settings.HUGGINGFACE_API_KEY,
        task="text-generation",
        max_new_tokens=4096,
        temperature=0.01,  # HF endpoint doesn't support exactly 0
        do_sample=False,
        timeout=45,
    )
    return ChatHuggingFace(llm=endpoint, verbose=False)


def _cascade_model(tier: str) -> BaseChatModel:
    """Groq (primary, fast) → HuggingFace (fallback). Uses both free quotas automatically.

    Flow: every call goes to Groq first. If Groq returns a rate-limit (429) or
    server error (5xx), LangChain transparently retries the same prompt on
    HuggingFace — the caller sees a normal response with no extra code needed.
    """
    primary = _groq_model(tier)
    fallback = _huggingface_model(tier)

    # Inject token callback into each underlying model directly so usage is
    # tracked regardless of which branch of the fallback chain fires.
    cb = _get_token_cb()
    for m in (primary, fallback):
        existing = list(getattr(m, "callbacks", None) or [])
        if not any(type(c) is type(cb) for c in existing):
            try:
                m.callbacks = existing + [cb]
            except (ValueError, AttributeError):
                pass

    # Only fall back on transient errors — rate limits and server-side failures.
    # Do NOT catch ValueError/TypeError/JSONDecodeError here; those are logic bugs.
    try:
        from groq import APIConnectionError as GroqAPIConnectionError
        from groq import APIStatusError as GroqAPIStatusError
        from groq import RateLimitError as GroqRateLimitError

        transient = (GroqRateLimitError, GroqAPIStatusError, GroqAPIConnectionError)
    except ImportError:
        transient = (Exception,)

    return primary.with_fallbacks(
        [fallback],
        exceptions_to_handle=transient,
    )
