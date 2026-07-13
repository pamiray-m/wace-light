from __future__ import annotations

import re


class PromptMinimizer:
    """
    Reduces prompt payload size: collapses whitespace and truncates.
    Applied before masking so character offsets remain valid.
    """

    def __init__(self, max_chars: int = 12_000) -> None:
        self._max_chars = max_chars

    def minimize(self, text: str) -> str:
        # Collapse runs of whitespace (but preserve newlines for readability)
        minimized = re.sub(r'[ \t]+', ' ', text).strip()
        minimized = re.sub(r'\n{3,}', '\n\n', minimized)

        if len(minimized) > self._max_chars:
            minimized = minimized[: self._max_chars] + "\n... [TRUNCATED BY SAIb]"

        return minimized


minimizer = PromptMinimizer()
