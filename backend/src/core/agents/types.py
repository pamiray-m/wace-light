"""
D1 — Agent Type enumeration.

AgentType is the canonical classification of every agent in the registry.
All downstream enforcement (mode governance, tool access, certification,
console) reads agent_type from AgentModel to determine which rule set applies.

INTERNAL
    Original agent class.  Behavior is unchanged from the pre-D1 system.

DAG (Digital Agent)
    Externally deployable, licensed, governed agent.  Subject to additional
    validation layers (D2–D14) that are routed through DAGConstraintHook.
    DAG agents are restricted by default and may not bypass normal code flow.

Ownership
---------
This file is owned by D1.  No other packet may redefine or alias AgentType.
Import it via: from src.core.agents.types import AgentType
"""

from enum import Enum


class AgentType(str, Enum):
    """Classification of every registered agent."""

    INTERNAL = "INTERNAL"
    # Original agent class.  No additional constraints beyond existing architecture.

    DAG = "DAG"
    # Digital Agent — externally deployable, licensed, and governed.
    # All DAG agents are routed through DAGConstraintHook before any
    # operation that is sensitive to agent classification.
