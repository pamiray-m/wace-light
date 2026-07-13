"""
Infusion — Google Gemini provider.

Requires GEMINI_API_KEY. Uses gemini-1.5-pro via the Generative Language API.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_MODEL   = "gemini-1.5-pro"
_TIMEOUT = 60


def _api_url(api_key: str) -> str:
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{_MODEL}:generateContent?key={api_key}"
    )


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        self._api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    def is_available(self) -> bool:
        return bool(self._api_key)

    def complete(self, prompt: str, system: str = "") -> str:
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

        parts = []
        if system:
            parts.append({"text": f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}"})
        else:
            parts.append({"text": prompt})

        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": 2048},
        }

        resp = httpx.post(
            _api_url(self._api_key),
            headers={"Content-Type": "application/json"},
            json=body,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
