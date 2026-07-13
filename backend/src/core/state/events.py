"""
TransitionEvent — immutable audit record for every agent state transition.

Every successful call to StateMachine.transition_state() produces one
TransitionEvent.  The event is:
  - returned to the caller
  - appended to the active backend (in-memory by default; SQLite when P6
    injects a SQLiteEventBackend via set_event_backend())

Backend protocol
----------------
The module-level record_event / get_audit_log / clear_audit_log functions
delegate to a swappable _current_backend.  The default backend is an
in-memory list so Packet 3 tests continue to work unchanged.

Packet 6 replaces the backend at app startup via:

    from src.core.state.events import set_event_backend
    from src.observability.events import SQLiteEventBackend
    set_event_backend(SQLiteEventBackend(session))
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from .enums import AgentState, Authority


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TransitionEvent(BaseModel):
    """
    Immutable record of a single agent lifecycle state transition.

    Fields
    ------
    event_id    : Unique identifier for this audit record.
    agent_id    : The agent that transitioned.
    product_id  : Tenant scope — preserved for cross-event correlation.
    from_state  : State before the transition.
    to_state    : State after the transition.
    authority   : The mAIb authority class that authorized the transition.
    actor       : Specific identity string (e.g. "user:john", "system:adapter").
    reason      : Human-readable justification (optional but encouraged).
    occurred_at : UTC timestamp of the transition.
    """

    event_id:    str          = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id:    str
    product_id:  str
    from_state:  AgentState
    to_state:    AgentState
    authority:   Authority
    actor:       str
    reason:      str          = ""
    occurred_at: datetime     = Field(default_factory=_now)

    model_config = {"frozen": True}   # events are immutable once created


# ---------------------------------------------------------------------------
# EventBackend protocol — swappable by Packet 6
# ---------------------------------------------------------------------------

@runtime_checkable
class EventBackend(Protocol):
    """
    Protocol that any event backend must satisfy.

    Implementations:
      _InMemoryBackend  — default, in-process list (P3 tests)
      SQLiteEventBackend — persistent SQLite (P6 production)
    """

    def record(self, event: TransitionEvent) -> None: ...

    def query(
        self,
        agent_id: Optional[str],
        product_id: Optional[str],
    ) -> list[TransitionEvent]: ...

    def clear(self) -> None: ...


class _InMemoryBackend:
    """Default in-memory backend — matches pre-P6 behaviour exactly."""

    def __init__(self) -> None:
        self._log: list[TransitionEvent] = []

    def record(self, event: TransitionEvent) -> None:
        self._log.append(event)

    def query(
        self,
        agent_id: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> list[TransitionEvent]:
        events = self._log
        if agent_id is not None:
            events = [e for e in events if e.agent_id == agent_id]
        if product_id is not None:
            events = [e for e in events if e.product_id == product_id]
        return list(events)

    def clear(self) -> None:
        self._log.clear()


_current_backend: EventBackend = _InMemoryBackend()


def set_event_backend(backend: EventBackend) -> None:
    """
    Replace the active event backend.

    Called by Packet 6 during app startup to swap in SQLiteEventBackend.
    Safe to call multiple times (e.g. in tests for reset).
    """
    global _current_backend
    _current_backend = backend


def reset_to_memory_backend() -> None:
    """Reset to a fresh in-memory backend.  Used in tests."""
    global _current_backend
    _current_backend = _InMemoryBackend()


# ---------------------------------------------------------------------------
# Public interface (unchanged since Packet 3)
# ---------------------------------------------------------------------------

def record_event(event: TransitionEvent) -> None:
    """Append a transition event to the active backend."""
    _current_backend.record(event)


def get_audit_log(
    agent_id: Optional[str] = None,
    product_id: Optional[str] = None,
) -> list[TransitionEvent]:
    """
    Retrieve recorded events, optionally filtered by agent_id and/or product_id.

    Delegates to the active backend (in-memory or SQLite).
    """
    return _current_backend.query(agent_id=agent_id, product_id=product_id)


def clear_audit_log() -> None:
    """Clear the active backend.  Used in tests."""
    _current_backend.clear()
