"""
Enumerations for the Knowledge & Skill System (Packet 8).

SkillStatus  — lifecycle states a skill package passes through before deployment.
SkillAuthority — who may authorize skill lifecycle transitions.

Design note
-----------
SkillAuthority is intentionally separate from Packet 3's Authority enum:
Layer 1 agents (Knowledge-Director, Oracle, Standards-Agent) do not exist
in the runtime lifecycle authority model but are first-class actors here.
"""

from __future__ import annotations

from enum import Enum


class SkillStatus(str, Enum):
    """
    Governed lifecycle states for a SkillPackage.

    State machine (see lifecycle.py):
      DRAFT → PROPOSED → VALIDATED → APPROVED → DEPLOYED → DEPRECATED
      PROPOSED → DRAFT  (rejection path — send back for rework)
      Any → DEPRECATED  (Architect force-deprecate)
    """
    DRAFT       = "DRAFT"
    PROPOSED    = "PROPOSED"
    VALIDATED   = "VALIDATED"
    APPROVED    = "APPROVED"
    DEPLOYED    = "DEPLOYED"
    DEPRECATED  = "DEPRECATED"


class SkillAuthority(str, Enum):
    """
    Authority classes that may authorize skill lifecycle transitions.

    Layer 0 (sovereignty) authorities have full governance rights.
    Layer 1 authorities are scoped to their governance role.

    Oracle may PROPOSE but never DEPLOY — this is the primary Oracle restraint.
    """
    # Layer 0 — full authority
    ARCHITECT           = "Architect"
    DEPUTY              = "Deputy"

    # Layer 1 — scoped authority
    KNOWLEDGE_DIRECTOR  = "KnowledgeDirector"
    STANDARDS_AGENT     = "StandardsAgent"
    ORACLE              = "Oracle"
    LAWYER              = "Lawyer"

    # Internal system calls (e.g. seeding initial DRAFT records)
    SYSTEM              = "System"
