"""
Infusion — Perplexity provider.

Requires PERPLEXITY_API_KEY. Uses sonar-pro via the OpenAI-compatible
Perplexity chat completions endpoint.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://api.perplexity.ai/chat/completions"
_MODEL   = "sonar-pro"
_TIMEOUT = 60


class PerplexityProvider:
    name = "perplexity"

    def __init__(self) -> None:
        self._api_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()

    def is_available(self) -> bool:
        return bool(self._api_key)

    def complete(self, prompt: str, system: str = "") -> str:
        if not self._api_key:
            raise RuntimeError("PERPLEXITY_API_KEY not set")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = httpx.post(
            _API_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type":  "application/json",
            },
            json={"model": _MODEL, "messages": messages, "max_tokens": 2048},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
