from __future__ import annotations

import re
from typing import List

from .base import BaseDetector, SensitiveEntity


class FinanceDetector(BaseDetector):
    """Detects financial identifiers: credit cards, IBANs."""

    PATTERNS = {
        # SA IBAN first — longer match wins deduplication over credit card digits
        "IBAN_SA": r"\bSA\d{2}(?:[ ]?\d{4}){5}\b",
        # 13–19 digit card numbers with optional separators
        "CREDIT_CARD": r"\b(?:\d{4}[- ]?){3}\d{1,4}\b",
        # Generic IBAN: 2 letters + 2 digits + up to 30 alphanum
        "IBAN": r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b",
        # Swift/BIC: 8 or 11 chars (4 bank + 2 country + 2 location + optional 3)
        "SWIFT_BIC": r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b",
    }

    def detect(self, text: str) -> List[SensitiveEntity]:
        entities: List[SensitiveEntity] = []
        for entity_type, pattern in self.PATTERNS.items():
            for match in re.finditer(pattern, text):
                entities.append(SensitiveEntity(
                    type=entity_type,
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                ))
        return entities

    @property
    def supported_types(self) -> List[str]:
        return list(self.PATTERNS.keys())
