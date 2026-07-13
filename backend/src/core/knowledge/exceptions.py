"""
Domain exceptions for the Knowledge & Skill System (Packet 8).

All exceptions derive from KnowledgeError so callers can catch the family.
"""

from __future__ import annotations


class KnowledgeError(Exception):
    """Base exception for all Packet 8 domain errors."""


class CrossProductAccessError(KnowledgeError):
    """
    Raised when a query attempts to access knowledge artifacts that belong
    to a different product_id than the requester's context.

    Per contract: "A vector query belonging to Product A MUST fail or return
    empty if querying a context mapped to Product B."
    """


class SkillNotFound(KnowledgeError):
    """Skill package does not exist or does not belong to the given product."""


class PlaybookNotFound(KnowledgeError):
    """Playbook does not exist or does not belong to the given product."""


class MemoryContextNotFound(KnowledgeError):
    """Memory context record does not exist for the given agent/product."""


class UnauthorizedSkillWrite(KnowledgeError):
    """
    Raised when a write is attempted by an authority that does not hold
    the required permission for that transition.

    Per contract: "If OpenClaw tries to push back or write modifications
    directly to the memory arrays, the Knowledge API physically rejects
    the requests."
    """


class InvalidSkillTransition(KnowledgeError):
    """
    Raised when a requested lifecycle transition is not permitted by the
    SkillLifecycleEngine policy matrix.
    """


class TerminalSkillError(KnowledgeError):
    """Raised when attempting to transition a DEPRECATED skill."""
