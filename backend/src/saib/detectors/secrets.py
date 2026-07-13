from __future__ import annotations

import re
from typing import List

from .base import BaseDetector, SensitiveEntity


class SecretsDetector(BaseDetector):
    """
    Detects API keys, tokens, and credential patterns.

    AOS-specific: mAIb Tech operations involve API keys for third-party
    integrations. These must never be sent verbatim to external LLMs.
    """

    PATTERNS = {
        # Anthropic API keys: sk-ant-...
        "ANTHROPIC_KEY": r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b",
        # OpenAI keys: sk-...
        "OPENAI_KEY": r"\bsk-[A-Za-z0-9]{20,}\b",
        # Generic API key / token assignment: api_key=XXX, token: XXX
        "API_KEY": r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9\-_\.]{16,})['\"]?",
        # Password assignment: password=XXX, passwd: XXX
        "PASSWORD": r"(?:password|passwd|pwd)\s*[:=]\s*['\"]?(\S{8,})['\"]?",
        # AWS access keys: AKIA...
        "AWS_ACCESS_KEY": r"\bAKIA[A-Z0-9]{16}\b",
        # JWT tokens: three base64url segments
        "JWT": r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
    }

    def detect(self, text: str) -> List[SensitiveEntity]:
        entities: List[SensitiveEntity] = []
        for entity_type, pattern in self.PATTERNS.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities.append(SensitiveEntity(
                    type=entity_type,
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    score=1.0,
                ))
        return entities

    @property
    def supported_types(self) -> List[str]:
        return list(self.PATTERNS.keys())
