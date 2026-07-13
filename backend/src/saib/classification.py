from __future__ import annotations

from enum import Enum
from typing import List

from .detectors.base import SensitiveEntity


class DataClassification(str, Enum):
    PUBLIC       = "PUBLIC"        # No sensitive content detected
    INTERNAL     = "INTERNAL"      # Org-internal keywords; no entities
    CONFIDENTIAL = "CONFIDENTIAL"  # PII / finance / credential entities present
    RESTRICTED   = "RESTRICTED"    # Explicit restricted-data keywords


_RESTRICTED_KEYWORDS = [
    "top secret", "highly confidential", "do not distribute",
    "noforn", "classified",
]

_INTERNAL_KEYWORDS = [
    "internal use only", "internal only", "confidential", "private",
    "not for public", "proprietary",
]


class DataClassifier:
    """Classifies prompt text based on keyword signals and entity presence."""

    def classify(
        self,
        text: str,
        entities: List[SensitiveEntity],
    ) -> DataClassification:
        lower = text.lower()

        # 1. RESTRICTED wins over everything
        for kw in _RESTRICTED_KEYWORDS:
            if kw in lower:
                return DataClassification.RESTRICTED

        # 2. CONFIDENTIAL: any sensitive entity, or credential keyword
        if entities:
            return DataClassification.CONFIDENTIAL

        for kw in _INTERNAL_KEYWORDS:
            if kw in lower:
                return DataClassification.INTERNAL

        return DataClassification.PUBLIC


classifier = DataClassifier()
