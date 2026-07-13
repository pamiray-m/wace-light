from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class SensitiveEntity:
    """A span of text identified as sensitive by a detector."""
    type: str      # e.g. "EMAIL", "CREDIT_CARD", "API_KEY"
    value: str     # the raw matched string
    start: int     # inclusive character offset
    end: int       # exclusive character offset
    score: float = 1.0

    def __repr__(self) -> str:
        return f"<Entity {self.type}: {self.value!r}>"


class BaseDetector(ABC):
    """Abstract base for all SAIb entity detectors."""

    @abstractmethod
    def detect(self, text: str) -> List[SensitiveEntity]:
        """Return all sensitive entities found in text."""

    @property
    @abstractmethod
    def supported_types(self) -> List[str]:
        """Entity type labels this detector recognises."""
