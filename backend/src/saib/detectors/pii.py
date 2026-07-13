from __future__ import annotations

import re
from typing import List

from .base import BaseDetector, SensitiveEntity


class PIIDetector(BaseDetector):
    """Detects personal identifiable information: emails, phones, national IDs, IPs."""

    PATTERNS = {
        "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        # GCC / Saudi phones: +9665xxxxxxxx, 009665xxxxxxxx, 05xxxxxxxx
        "PHONE_GCC": r"(?:\b05|(?<!\w)\+9665|(?<!\w)009665)\d{8}\b",
        # Generic international phone: +1-..., +44-...
        "PHONE_INTL": r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b",
        # KSA national ID: 10 digits starting with 1 or 2
        "NATIONAL_ID_KSA": r"\b[12]\d{9}\b",
        # IPv4
        "IP_ADDR": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        # Passport-like: 2 letters + 7 digits
        "PASSPORT": r"\b[A-Z]{2}\d{7}\b",
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
