"""
W6.1 — Model router.

Picks the cheapest Claude model that can plausibly serve a given prompt.
Wired into `LLMGateway.complete` so any caller that doesn't pass `model=`
explicitly inherits the routing decision.

Why this exists
---------------
The W5.2 telemetry exposed the per-model cost reality: every call without
`model=` was paying Sonnet rates regardless of the task. The Board's
ADVISORY consultations, simple agent acknowledgements, and short retrieval
queries are all routable to Haiku at ~5× cost savings without quality loss.

Routing rules (default)
-----------------------
1. Caller explicitly passed `model=` → router is NEVER consulted.
2. `risk_hint == "high"` → Opus.
3. `task_hint` matches an env-configured override → use that model.
4. Combined prompt+system length > LARGE_PROMPT_CHARS (8000) → Opus.
5. Combined prompt+system length < SMALL_PROMPT_CHARS (1500) AND
   no high-stakes signal → Haiku.
6. Otherwise → Sonnet (default).

Env overrides
-------------
`AOS_LLM_DEFAULT_MODEL`        — pin every router decision to this model.
`AOS_LLM_SMALL_PROMPT_CHARS`   — boundary for Haiku (default 1500).
`AOS_LLM_LARGE_PROMPT_CHARS`   — boundary for Opus  (default 8000).
`AOS_LLM_MODEL_OVERRIDES`      — JSON map `{task_hint: model_id}` (default {}).

Disabling
---------
`AOS_LLM_ROUTER=off` returns the LLMGateway's normal default model, leaving
behaviour identical to pre-W6.1.

Telemetry
---------
Every routing decision increments
`aos_llm_router_decisions_total{model, reason}` so /metrics shows the cost
mix at a glance. reason ∈ {default, small_prompt, large_prompt, risk_high,
task_override, env_pin, disabled}.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from src.core.observability.prom import LabeledCounter

_log = logging.getLogger(__name__)


# Match the gateway's default for backwards compatibility.
DEFAULT_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL   = "claude-haiku-4-5"
SONNET_MODEL  = "claude-sonnet-4-6"
OPUS_MODEL    = "claude-opus-4-7"


router_decisions_total = LabeledCounter(
    "aos_llm_router_decisions_total",
    "Model router decisions by chosen model and reason.",
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _is_enabled() -> bool:
    raw = (os.environ.get("AOS_LLM_ROUTER", "on") or "on").strip().lower()
    return raw not in ("off", "0", "false", "no")


def _env_pin() -> Optional[str]:
    raw = (os.environ.get("AOS_LLM_DEFAULT_MODEL", "") or "").strip()
    return raw or None


def _small_threshold() -> int:
    raw = (os.environ.get("AOS_LLM_SMALL_PROMPT_CHARS", "") or "").strip()
    if not raw:
        return 1500
    try:
        v = int(raw)
        return v if v > 0 else 1500
    except (TypeError, ValueError):
        return 1500


def _large_threshold() -> int:
    raw = (os.environ.get("AOS_LLM_LARGE_PROMPT_CHARS", "") or "").strip()
    if not raw:
        return 8000
    try:
        v = int(raw)
        return v if v > 0 else 8000
    except (TypeError, ValueError):
        return 8000


def _task_overrides() -> dict[str, str]:
    raw = (os.environ.get("AOS_LLM_MODEL_OVERRIDES", "") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except Exception as exc:
        _log.warning("AOS_LLM_MODEL_OVERRIDES invalid (%s); ignoring", exc)
    return {}


# ---------------------------------------------------------------------------
# Routing decision
# ---------------------------------------------------------------------------

def choose_model(
    prompt: str,
    system: str = "",
    task_hint: Optional[str] = None,
    risk_hint: Optional[str] = None,
) -> str:
    """Return the model_id this prompt should route to.

    Reads env on every call. Records a `router_decisions_total` sample
    labeled by chosen model + reason so the cost mix is visible on /metrics.
    """
    if not _is_enabled():
        router_decisions_total.inc(labels={"model": DEFAULT_MODEL, "reason": "disabled"})
        return DEFAULT_MODEL

    pin = _env_pin()
    if pin:
        router_decisions_total.inc(labels={"model": pin, "reason": "env_pin"})
        return pin

    # Risk hint short-circuits to Opus regardless of length.
    if risk_hint and risk_hint.lower() == "high":
        router_decisions_total.inc(labels={"model": OPUS_MODEL, "reason": "risk_high"})
        return OPUS_MODEL

    overrides = _task_overrides()
    if task_hint and task_hint in overrides:
        choice = overrides[task_hint]
        router_decisions_total.inc(labels={"model": choice, "reason": "task_override"})
        return choice

    combined_len = len(prompt or "") + len(system or "")
    if combined_len >= _large_threshold():
        router_decisions_total.inc(labels={"model": OPUS_MODEL, "reason": "large_prompt"})
        return OPUS_MODEL
    if combined_len <= _small_threshold():
        router_decisions_total.inc(labels={"model": HAIKU_MODEL, "reason": "small_prompt"})
        return HAIKU_MODEL

    router_decisions_total.inc(labels={"model": SONNET_MODEL, "reason": "default"})
    return SONNET_MODEL
