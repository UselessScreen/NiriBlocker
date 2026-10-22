"""Tier-1 AI provider selection and clients.

The daemon supports the existing OpenRouter provider, Google's Gemini API, and
local OpenAI-compatible endpoints such as Ollama or LM Studio. Configuration is
stored in the normal daemon config file and edited through the desktop Settings
page.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from daemon import config as daemon_config
from daemon.grants import openrouter

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "openrouter"
DEFAULT_GOOGLE_MODEL = "gemini-2.5-flash"
DEFAULT_LOCAL_MODEL = "llama3.2"
DEFAULT_LOCAL_URL = "http://127.0.0.1:11434/v1"


class AIProviderError(RuntimeError):
    """Any provider configuration, network, or response-shape failure."""


@dataclass(frozen=True)
class AIConfig:
    provider: str
    model: str
    api_key: str = ""
    base_url: str = ""

    def __repr__(self) -> str:
        return (
            f"AIConfig(provider={self.provider!r}, model={self.model!r}, "
            f"base_url={self.base_url!r}, api_key=***)"
        )


class GoogleClient:
    """Minimal Gemini ``generateContent`` client."""

    def __init__(
        self,
        config: AIConfig,
        *,
        timeout: float = openrouter.DEFAULT_TIMEOUT_SECONDS,
        attempts: int = openrouter.DEFAULT_ATTEMPTS,
        urlopen: Callable[..., object] | None = None,
    ) -> None:
        if not config.api_key:
            raise AIProviderError("Google API key not configured")
        self._config = config
        self._timeout = timeout
        self._attempts = max(1, attempts)
        self._urlopen = urlopen or urllib.request.urlopen

    def chat(self, messages: list[dict[str, str]]) -> str:
        system_parts = [
            message["content"] for message in messages if message["role"] == "system"
        ]
        contents = [
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
            for message in messages
            if message["role"] != "system"
        ]
        payload: dict[str, object] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(self._config.model, safe='')}:generateContent"
            f"?key={urllib.parse.quote(self._config.api_key, safe='')}"
        )
        request = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        last_error: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            try:
                with self._urlopen(request, timeout=self._timeout) as response:  # type: ignore[call-arg]
                    return self._extract_content(response.read())
            except AIProviderError:
                raise
            except Exception as error:
                last_error = error
                logger.warning(
                    "Google AI attempt %d/%d failed: %s",
                    attempt,
                    self._attempts,
                    type(error).__name__,
                )
        raise AIProviderError(
            f"Google AI unreachable after {self._attempts} attempts: "
            f"{type(last_error).__name__}"
        )

    @staticmethod
    def _extract_content(body: bytes) -> str:
        try:
            content = json.loads(body)["candidates"][0]["content"]["parts"][0]["text"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise AIProviderError(
                f"Malformed Google AI response: {type(error).__name__}"
            ) from error
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("Empty Google AI completion content")
        return content


def load_user_tier_config() -> AIConfig:
    """Load the user-tier provider from the persisted daemon configuration."""
    settings = daemon_config.get_config().ai
    provider = settings.provider.strip().lower()
    if provider in {"gemini", "google", "google-gemini"}:
        return AIConfig(
            provider="google",
            model=(
                settings.model
                if settings.model and settings.model != openrouter.DEFAULT_MODEL
                else DEFAULT_GOOGLE_MODEL
            ),
            api_key=settings.api_key,
        )
    if provider in {"local", "ollama", "lmstudio", "openai-compatible"}:
        return AIConfig(
            provider="local",
            model=(
                settings.model
                if settings.model and settings.model != openrouter.DEFAULT_MODEL
                else DEFAULT_LOCAL_MODEL
            ),
            api_key=settings.api_key,
            base_url=settings.base_url or DEFAULT_LOCAL_URL,
        )
    if provider != "openrouter":
        raise AIProviderError(f"Unsupported AI provider: {provider}")
    return AIConfig(
        provider="openrouter",
        model=settings.model or openrouter.DEFAULT_MODEL,
        api_key=settings.api_key,
        base_url=settings.base_url or openrouter.DEFAULT_BASE_URL,
    )


def create_client(
    config: AIConfig,
    *,
    timeout: float = openrouter.DEFAULT_TIMEOUT_SECONDS,
    attempts: int = openrouter.DEFAULT_ATTEMPTS,
    urlopen: Callable[..., object] | None = None,
):
    """Create the configured client; unconfigured providers fail closed."""
    if config.provider == "google":
        return GoogleClient(config, timeout=timeout, attempts=attempts, urlopen=urlopen)
    if config.provider == "local":
        if not config.base_url:
            raise AIProviderError("Local AI URL not configured")
        return openrouter.OpenRouterClient(
            openrouter.OpenRouterConfig(
                api_key=config.api_key or "local",
                model=config.model,
                base_url=config.base_url,
            ),
            timeout=timeout,
            attempts=attempts,
            urlopen=urlopen,
        )
    if not config.api_key:
        raise AIProviderError("OpenRouter API key not configured")
    return openrouter.OpenRouterClient(
        openrouter.OpenRouterConfig(
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
        ),
        timeout=timeout,
        attempts=attempts,
        urlopen=urlopen,
    )
