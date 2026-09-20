"""config.py: single source of truth for settings.
Reads .env locally and st.secrets on Streamlit Community Cloud."""
import os

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("OTEL_SDK_DISABLED", "true")  # no telemetry calls during a live demo


def _get(key: str, default: str = "") -> str:
    val = os.getenv(key)
    if val:
        return val
    try:  # Streamlit Community Cloud secrets
        import streamlit as st

        return str(st.secrets.get(key, default))
    except Exception:
        return default


ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")  # optional; only if you ever switch back
if ANTHROPIC_API_KEY:
    os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

TAVILY_API_KEY = _get("TAVILY_API_KEY")  # optional; empty -> DuckDuckGo fallback
GITHUB_TOKEN = _get("GITHUB_TOKEN")  # optional; raises GitHub's limit from 60 to 5,000 requests/hour

_PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key": _get("GROQ_API_KEY"),
        # Groq's free tier counts prompt + max_tokens against a small per-minute limit, so keep this low.
        "max_tokens": int(_get("HIREFLOW_GROQ_MAX_TOKENS", "2500")),
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key": _get("GEMINI_API_KEY"),
        "max_tokens": int(_get("HIREFLOW_GEMINI_MAX_TOKENS", "8000")),  # room for JSON + thinking tokens
    },
}

ROLE_MODELS = {  # "provider:model", overridable in .env
    "extract": _get("HIREFLOW_MODEL_EXTRACT", "gemini:gemini-3.6-flash"),
    "reason": _get("HIREFLOW_MODEL_REASON", "gemini:gemini-3.5-flash"),
    "light": _get("HIREFLOW_MODEL_LIGHT", "groq:qwen/qwen3.8-27b"),
    "fallback": _get("HIREFLOW_MODEL_FALLBACK", "gemini:gemini-3.5-flash-lite"),
}

# Hard ceiling: even a bad .env can't push an agent past 8 iterations.
MAX_ITER = max(1, min(int(_get("HIREFLOW_MAX_ITER", "5")), 8))
MAX_TOOL_CALLS = max(1, min(int(_get("HIREFLOW_MAX_TOOL_CALLS", "10")), 25))  # per candidate
MAX_RPM = max(1, int(_get("HIREFLOW_MAX_RPM", "10")))  # crew-level throttle; Gemini free tier is about 10-15/min
MAX_OUTPUT_TOKENS = max(1000, int(_get("HIREFLOW_MAX_OUTPUT_TOKENS", "6000")))  # Anthropic only


def role_available(role: str) -> bool:
    """True if the provider behind this role has an API key configured."""
    provider = ROLE_MODELS[role].partition(":")[0]
    if provider == "anthropic":
        return bool(ANTHROPIC_API_KEY)
    return bool(_PROVIDERS.get(provider, {}).get("key"))


def build_llm(role: str = "reason"):
    """One place that decides which model each agent role uses."""
    from crewai import LLM

    provider, _, model = ROLE_MODELS[role].partition(":")
    if provider == "anthropic":
        return LLM(model=f"anthropic/{model}", max_tokens=MAX_OUTPUT_TOKENS)
    cfg = _PROVIDERS[provider]
    return LLM(model=f"openai/{model}", base_url=cfg["base_url"], api_key=cfg["key"], max_tokens=cfg["max_tokens"])