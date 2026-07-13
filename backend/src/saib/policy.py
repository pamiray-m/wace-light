"""
SAIb Policy Engine for AOS.

AOS-specific adaptation of GAIO's policy model. Key difference: AOS sends
prompts to Claude (Anthropic) which is the trusted execution engine — there
is no "internal only" mode that blocks all external calls. Policy instead:

  RESTRICTED   → BLOCK entirely (never leaves the system)
  CONFIDENTIAL → MASK and allow (entities replaced with placeholders)
  INTERNAL     → MINIMIZE and allow (whitespace strip + truncation)
  PUBLIC       → ALLOW as-is

Controlled by AOS_SAIB_MODE env var:
  OFF     — bypass all checking (tests / local dev without API key)
  DETECT  — scan and log detections but never block or mask
  MASK    — default production: mask CONFIDENTIAL, block RESTRICTED
  STRICT  — block CONFIDENTIAL too (maximum enterprise posture)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

from .classification import DataClassification
from .detectors.base import SensitiveEntity


class SAIbMode(str, Enum):
    OFF    = "OFF"
    DETECT = "DETECT"
    MASK   = "MASK"
    STRICT = "STRICT"


class PolicyOutcome(str, Enum):
    ALLOW  = "ALLOW"   # send prompt unchanged
    MASK   = "MASK"    # apply masking before sending
    BLOCK  = "BLOCK"   # do not send; raise error


@dataclass(frozen=True)
class PolicyResult:
    outcome:          PolicyOutcome
    classification:   DataClassification
    reason:           str
    apply_masking:    bool = False
    apply_minimize:   bool = False
    entities_found:   int  = 0


def _current_mode() -> SAIbMode:
    raw = os.environ.get("AOS_SAIB_MODE", "MASK").upper()
    try:
        return SAIbMode(raw)
    except ValueError:
        return SAIbMode.MASK


class SAIbPolicyEngine:
    """Determines the egress policy given classification and mode."""

    def evaluate(
        self,
        classification: DataClassification,
        entities: List[SensitiveEntity],
        mode: SAIbMode | None = None,
    ) -> PolicyResult:
        effective_mode = mode if mode is not None else _current_mode()

        # OFF — pass everything through untouched
        if effective_mode == SAIbMode.OFF:
            return PolicyResult(
                outcome=PolicyOutcome.ALLOW,
                classification=classification,
                reason="SAIb OFF: bypass enabled",
                entities_found=len(entities),
            )

        # DETECT — scan and log but never block or mask
        if effective_mode == SAIbMode.DETECT:
            return PolicyResult(
                outcome=PolicyOutcome.ALLOW,
                classification=classification,
                reason=f"DETECT mode: {len(entities)} entities logged, not masked",
                entities_found=len(entities),
            )

        # RESTRICTED always blocked regardless of mode
        if classification == DataClassification.RESTRICTED:
            return PolicyResult(
                outcome=PolicyOutcome.BLOCK,
                classification=classification,
                reason="RESTRICTED data detected — prompt blocked by SAIb policy",
                entities_found=len(entities),
            )

        # STRICT mode: block CONFIDENTIAL as well
        if effective_mode == SAIbMode.STRICT and classification == DataClassification.CONFIDENTIAL:
            return PolicyResult(
                outcome=PolicyOutcome.BLOCK,
                classification=classification,
                reason="STRICT mode: CONFIDENTIAL data blocked",
                entities_found=len(entities),
            )

        # MASK / STRICT with INTERNAL or PUBLIC
        if classification == DataClassification.CONFIDENTIAL:
            return PolicyResult(
                outcome=PolicyOutcome.MASK,
                classification=classification,
                reason=f"CONFIDENTIAL: {len(entities)} entities will be masked",
                apply_masking=True,
                apply_minimize=True,
                entities_found=len(entities),
            )

        # INTERNAL or PUBLIC
        return PolicyResult(
            outcome=PolicyOutcome.ALLOW,
            classification=classification,
            reason="Standard traffic — minimizing only",
            apply_minimize=True,
            entities_found=len(entities),
        )


policy_engine = SAIbPolicyEngine()
