"""
Canonical enumerations for the mAIb Agent State Machine.

These are the authoritative definitions for agent lifecycle states and the
transition authority roles.  The Agent Registry (Packet 2) imports AgentState
from here so there is exactly one definition of each state across the system.

Packet 3 owns this file.  Any future packet that needs state or authority
types must import from here — never redefine them.
"""

from enum import Enum


class AgentState(str, Enum):
    """
    Eight canonical lifecycle states for every mAIb agent.

    Ordering reflects the normal forward progression of an agent.
    Runtime engines are never the source of truth for these values;
    the mAIb Registry record is.
    """
    PROVISIONING = "PROVISIONING"   # Initializing in the mAIb Registry
    ACTIVE       = "ACTIVE"         # Registered and fully loaded
    IDLE         = "IDLE"           # Online but holding no tasks
    BUSY         = "BUSY"           # Executing instructions
    DEGRADED     = "DEGRADED"       # Encountered exceptions; Watcher alerted
    BLOCKED      = "BLOCKED"        # Governance hard-stop due to risk
    PAUSED       = "PAUSED"         # Halted via human oversight
    TERMINATED   = "TERMINATED"     # Offline permanently (terminal — no exit)


class Authority(str, Enum):
    """
    mAIb transition authority roles.

    These map to the authority classes defined in the agent-state-model contract.
    Each authority class has a strictly defined set of transitions it may assert;
    see src/core/state/policy.py for the complete matrix.

    Packet 3 spec lists: Lawyer, Watcher, CEO, System, Architect.
    Deputy is included as a Layer 0 peer of Architect but carries no transition
    rights in the current matrix — reserved for a future policy amendment.
    """
    ARCHITECT = "Architect"
    DEPUTY    = "Deputy"    # Layer 0 peer; rights reserved — see policy.py
    WATCHER   = "Watcher"
    LAWYER    = "Lawyer"
    CEO       = "CEO"
    SYSTEM    = "System"
