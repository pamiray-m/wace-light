"""
SAIbGuard — the single integration point for the Secure AI Bridge in AOS.

Usage inside LLMGateway
-----------------------
    from src.saib.guard import saib_guard, SAIbBlockedError

    guard_result = saib_guard.process(prompt, system)
    if guard_result.blocked:
        raise SAIbBlockedError(guard_result.block_reason)

    # LLM call with sanitised inputs
    response = llm_backend.complete(guard_result.safe_prompt, guard_result.safe_system)

    # Unmask: restore original values in the response
    final_text = saib_guard.unmask(response.text, guard_result.mapping)

GuardResult fields
------------------
blocked       : True when SAIb blocked the prompt (BLOCK outcome).
block_reason  : Human-readable reason when blocked.
safe_prompt   : The (possibly masked/minimized) prompt to send to the LLM.
safe_system   : The (possibly masked/minimized) system prompt.
mapping       : Placeholder → original value dict for unmasking.
entities      : List of detected entities (for logging/audit).
classification: DataClassification of the prompt.
policy_reason : Why the policy engine reached its decision.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .classification import DataClassification, classifier
from .detectors.base import SensitiveEntity
from .detectors.registry import detector_registry
from .minimizer import minimizer
from .policy import PolicyOutcome, SAIbMode, policy_engine

logger = logging.getLogger(__name__)


class SAIbBlockedError(RuntimeError):
    """Raised when SAIb blocks a prompt due to data classification policy."""

    def __init__(self, reason: str, classification: DataClassification | None = None) -> None:
        super().__init__(reason)
        self.classification = classification


@dataclass
class GuardResult:
    """Full result of a SAIb guard pass over a prompt+system pair."""

    blocked:        bool
    block_reason:   str                      = ""
    safe_prompt:    str                      = ""
    safe_system:    str                      = ""
    mapping:        Dict[str, str]           = field(default_factory=dict)
    entities:       List[SensitiveEntity]    = field(default_factory=list)
    classification: DataClassification       = DataClassification.PUBLIC
    policy_reason:  str                      = ""
    mode:           str                      = "MASK"


class SAIbGuard:
    """
    Orchestrates the full SAIb pipeline for AOS LLM calls.

    Pipeline (per call):
      1. Scan prompt + system for sensitive entities.
      2. Classify the combined text.
      3. Evaluate policy given mode (AOS_SAIB_MODE env var).
      4. If BLOCK → return blocked GuardResult.
      5. If MASK  → minimize then mask both prompt and system.
      6. If ALLOW → minimize only.

    The mapping returned in GuardResult is used after the LLM responds
    to restore original values via unmask().
    """

    def process(
        self,
        prompt: str,
        system: str = "",
    ) -> GuardResult:
        # W3.1 — honor AOS_GOVERNANCE_PROFILE when AOS_SAIB_MODE is unset.
        # When the per-mode env var IS set, it wins (operator override).
        explicit = os.environ.get("AOS_SAIB_MODE", "")
        if explicit:
            mode_raw = explicit.upper()
        else:
            try:
                from src.config.loader import saib_mode_default
                mode_raw = saib_mode_default().upper()
            except Exception:
                mode_raw = "MASK"
        try:
            mode = SAIbMode(mode_raw)
        except ValueError:
            mode = SAIbMode.MASK

        # Scan combined text so cross-field entities are caught
        combined = f"{system}\n{prompt}" if system else prompt
        entities = detector_registry.scan(combined)
        classification = classifier.classify(combined, entities)

        policy = policy_engine.evaluate(classification, entities, mode=mode)

        logger.debug(
            "SAIb: mode=%s classification=%s entities=%d outcome=%s reason=%r",
            mode.value,
            classification.value,
            len(entities),
            policy.outcome.value,
            policy.reason,
        )

        if policy.outcome == PolicyOutcome.BLOCK:
            logger.warning(
                "SAIb BLOCKED prompt: classification=%s reason=%r",
                classification.value,
                policy.reason,
            )
            return GuardResult(
                blocked=True,
                block_reason=policy.reason,
                classification=classification,
                policy_reason=policy.reason,
                entities=entities,
                mode=mode.value,
            )

        safe_prompt = prompt
        safe_system = system
        mapping: Dict[str, str] = {}

        if policy.apply_minimize:
            safe_prompt = minimizer.minimize(safe_prompt)
            if safe_system:
                safe_system = minimizer.minimize(safe_system)

        if policy.apply_masking:
            # Scan prompt and system separately for precise offset tracking
            prompt_entities  = detector_registry.scan(safe_prompt)
            safe_prompt, prompt_mapping = detector_registry.mask(safe_prompt, prompt_entities)
            mapping.update(prompt_mapping)

            if safe_system:
                system_entities  = detector_registry.scan(safe_system)
                safe_system, system_mapping = detector_registry.mask(safe_system, system_entities)
                # Merge: use unique placeholders so no collision
                # (type counters reset per-call, so EMAIL_1 in prompt vs EMAIL_1 in system
                # could collide. Re-number system placeholders if duplicates exist.)
                for k, v in system_mapping.items():
                    if k in mapping:
                        # rename: append _SYS suffix
                        new_key = k.replace("]", "_SYS]")
                        safe_system = safe_system.replace(k, new_key)
                        mapping[new_key] = v
                    else:
                        mapping[k] = v

            if mapping:
                logger.info(
                    "SAIb masked %d placeholder(s) before LLM call", len(mapping)
                )

        return GuardResult(
            blocked=False,
            safe_prompt=safe_prompt,
            safe_system=safe_system,
            mapping=mapping,
            entities=entities,
            classification=classification,
            policy_reason=policy.reason,
            mode=mode.value,
        )

    def unmask(self, text: str, mapping: Dict[str, str]) -> str:
        """Restore original values in the LLM response."""
        return detector_registry.unmask(text, mapping)


# Process-level singleton
saib_guard = SAIbGuard()
