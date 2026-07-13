"""
Kill switch (open-source edition) — a self-contained global halt for WACE.

Governance and agent runs check ``is_autonomy_halted()`` and refuse to act when
the switch is on. One flip halts everything; flip it back to resume.
"""

from __future__ import annotations

from typing import Optional


class KillSwitchService:
    def __init__(self) -> None:
        self._halted: bool = False
        self._reasons: list[str] = []
        self._states: dict = {}

    def activate(self, reason: str = "", updated_by: str = "") -> None:
        self._halted = True
        self._reasons = [reason or "halted"]

    def deactivate(self, reason: str = "", updated_by: str = "") -> None:
        self._halted = False
        self._reasons = []

    @property
    def halted(self) -> bool:
        return self._halted


kill_switch_service = KillSwitchService()


def is_autonomy_halted(scope: Optional[str] = None) -> bool:
    return kill_switch_service.halted


def halt_reasons(scope: Optional[str] = None) -> list[str]:
    return list(kill_switch_service._reasons)


def reset_for_tests() -> None:
    kill_switch_service.deactivate()
