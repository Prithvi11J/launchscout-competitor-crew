"""Central place for settings and for creating the LLM.

Every agent asks this file for its model, so switching models (or
providers) later means changing one function, not four agents.

Import this module BEFORE importing crewai anywhere else: it switches off
CrewAI's anonymous telemetry, and that switch must be set before crewai loads.
"""

import os

from dotenv import load_dotenv

# Read key=value pairs from .env into environment variables.
# Real environment variables win, which is how cloud hosts inject secrets.
load_dotenv()

# Privacy default: no usage telemetry leaves this machine unless you opt in.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

DEFAULT_MODEL = "gpt-5.4-mini"

# Placeholder values copied from .env.example count as "not set".
_PLACEHOLDERS = {"", "sk-your-key-here", "your-serper-key-here"}


class ConfigError(RuntimeError):
    """Raised when required settings are missing."""


def _read(name: str) -> str:
    value = os.getenv(name, "").strip()
    return "" if value in _PLACEHOLDERS else value


def get_api_key() -> str:
    key = _read("OPENAI_API_KEY")
    if not key:
        raise ConfigError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env "
            "and paste your OpenAI key into it."
        )
    return key


def get_serper_key() -> str | None:
    """Serper powers web search. None means the research agents can't go online."""
    return _read("SERPER_API_KEY") or None


def get_model_name() -> str:
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def get_llm(temperature: float | None = None):
    """Return a CrewAI LLM object that every agent can share.

    CrewAI has its own LLM wrapper (not LangChain's ChatOpenAI). The model
    string picks the provider; plain "gpt-..." names go to OpenAI.
    """
    from crewai import LLM  # imported here so telemetry settings above apply first

    kwargs = {"model": get_model_name(), "api_key": get_api_key(), "timeout": 120, "max_retries": 3}
    if temperature is not None:
        kwargs["temperature"] = temperature
    return LLM(**kwargs)
