"""Tests for grant-judge provider selection and Gemini requests."""

import json

import pytest

from daemon import config as daemon_config
from daemon.grants import ai


def test_google_config_from_persisted_settings(monkeypatch):
    monkeypatch.setattr(
        daemon_config,
        "_config",
        daemon_config.Config(
            ai=daemon_config.AIConfig(
                provider="google", model="gemini-test", api_key="key"
            )
        ),
    )
    config = ai.load_user_tier_config()
    assert config.provider == "google"
    assert config.model == "gemini-test"
    assert config.api_key == "key"


def test_local_config_does_not_require_api_key(monkeypatch):
    monkeypatch.setattr(
        daemon_config,
        "_config",
        daemon_config.Config(
            ai=daemon_config.AIConfig(
                provider="local", base_url="http://localhost:1234/v1"
            )
        ),
    )
    config = ai.load_user_tier_config()
    assert config == ai.AIConfig(
        provider="local",
        model=ai.DEFAULT_LOCAL_MODEL,
        base_url="http://localhost:1234/v1",
    )


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(
        daemon_config,
        "_config",
        daemon_config.Config(ai=daemon_config.AIConfig(provider="unknown")),
    )
    with pytest.raises(ai.AIProviderError, match="Unsupported AI provider"):
        ai.load_user_tier_config()


class _Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def test_google_client_sends_gemini_payload_and_extracts_text():
    captured = {}

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return _Response(
            b'{"candidates":[{"content":{"parts":[{"text":"{\\"decision\\":\\"deny\\"}"}]}}]}'
        )

    client = ai.GoogleClient(
        ai.AIConfig(provider="google", model="gemini-test", api_key="secret"),
        urlopen=urlopen,
    )
    result = client.chat(
        [
            {"role": "system", "content": "Rules"},
            {"role": "user", "content": "Request"},
        ]
    )

    assert result == '{"decision":"deny"}'
    assert "key=secret" in captured["url"]
    assert captured["payload"]["systemInstruction"]["parts"][0]["text"] == "Rules"
    assert captured["payload"]["contents"] == [{"role": "user", "parts": [{"text": "Request"}]}]


def test_local_provider_uses_openai_compatible_endpoint():
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"local reply"}}]}'

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        return _Response()

    client = ai.create_client(
        ai.AIConfig(
            provider="local",
            model="local-test",
            base_url="http://localhost:1234/v1",
        ),
        urlopen=urlopen,
    )

    assert client.chat([{"role": "user", "content": "Request"}]) == "local reply"
    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["payload"]["model"] == "local-test"
