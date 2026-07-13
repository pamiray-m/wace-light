"""
Infusion — OpenAI / ChatGPT provider.

Requires OPENAI_API_KEY. Uses gpt-4o via the OpenAI chat completions endpoint.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://api.openai.com/v1/chat/completions"
_MODEL   = "gpt-4o"
_TIMEOUT = 60


class OpenAIProvider:
    name = "chatgpt"

    def __init__(self) -> None:
        self._api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    def is_available(self) -> bool:
        return bool(self._api_key)

    def complete(self, prompt: str, system: str = "") -> str:
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

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
