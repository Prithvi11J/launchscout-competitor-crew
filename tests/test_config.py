"""Offline tests for the config module (no API calls)."""

import pytest

from launchscout import config


def test_placeholder_keys_count_as_missing(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-your-key-here")
    monkeypatch.setenv("SERPER_API_KEY", "your-serper-key-here")
    with pytest.raises(config.ConfigError):
        config.get_api_key()
    assert config.get_serper_key() is None


def test_model_defaults_and_override(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert config.get_model_name() == config.DEFAULT_MODEL
    monkeypatch.setenv("OPENAI_MODEL", "gpt-other")
    assert config.get_model_name() == "gpt-other"


def test_telemetry_off_by_default():
    import os

    assert os.environ["CREWAI_DISABLE_TELEMETRY"] == "true"


def test_get_llm_uses_configured_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4-mini")
    llm = config.get_llm()
    assert "gpt-5.4-mini" in llm.model
