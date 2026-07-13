from __future__ import annotations

from typing import Dict, List, Tuple

from .base import BaseDetector, SensitiveEntity
from .pii import PIIDetector
from .finance import FinanceDetector
from .secrets import SecretsDetector


class DetectorRegistry:
    """
    Aggregates all detectors and runs them in sequence.

    Deduplication: when two detectors match the same span, the longer
    match wins. Overlapping shorter spans are dropped.
    """

    def __init__(self) -> None:
        self._detectors: List[BaseDetector] = [
            PIIDetector(),
            FinanceDetector(),
            SecretsDetector(),
        ]

    def scan(self, text: str) -> List[SensitiveEntity]:
        """Run all detectors and return deduplicated entities."""
        raw: List[SensitiveEntity] = []
        for detector in self._detectors:
            raw.extend(detector.detect(text))

        # Sort by start position, then by length descending (longest wins)
        raw.sort(key=lambda e: (e.start, -(e.end - e.start)))

        deduped: List[SensitiveEntity] = []
        last_end = -1
        for entity in raw:
            if entity.start >= last_end:
                deduped.append(entity)
                last_end = entity.end

        return deduped

    def mask(
        self,
        text: str,
        entities: List[SensitiveEntity] | None = None,
    ) -> Tuple[str, Dict[str, str]]:
        """
        Replace each entity span with a typed placeholder.

        Returns (masked_text, mapping) where mapping maps each placeholder
        back to its original value for response unmasking.
        """
        if entities is None:
            entities = self.scan(text)

        # Assign placeholder IDs in forward order
        forward = sorted(entities, key=lambda e: e.start)
        type_counters: Dict[str, int] = {}
        entity_placeholders: List[Tuple[SensitiveEntity, str]] = []
        mapping: Dict[str, str] = {}

        for entity in forward:
            type_counters[entity.type] = type_counters.get(entity.type, 0) + 1
            placeholder = f"[{entity.type}_{type_counters[entity.type]}]"
            entity_placeholders.append((entity, placeholder))
            mapping[placeholder] = entity.value

        # Apply replacements backwards to preserve character offsets
        chars = list(text)
        for entity, placeholder in reversed(entity_placeholders):
            chars[entity.start:entity.end] = list(placeholder)

        return "".join(chars), mapping

    def unmask(self, text: str, mapping: Dict[str, str]) -> str:
        """Restore original values by replacing placeholders."""
        result = text
        for placeholder, original in mapping.items():
            result = result.replace(placeholder, original)
        return result

    @property
    def supported_types(self) -> List[str]:
        types: List[str] = []
        for d in self._detectors:
            types.extend(d.supported_types)
        return types


# Process-level singleton
detector_registry = DetectorRegistry()
