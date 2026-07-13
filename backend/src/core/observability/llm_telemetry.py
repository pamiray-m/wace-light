"""
W5.2 — LLM observability.

Wraps every call going through `src.llm.gateway.LLMGateway.complete()` with
timing, token counts, and outcome telemetry. Two surfaces:

1. Prometheus counters/gauges (scraped via /metrics):
     aos_llm_calls_total{model, via, status}
     aos_llm_tokens_total{model, direction}      direction ∈ {input, output}
     aos_llm_call_seconds_total{model, via}
     aos_llm_last_call_seconds{model, via}        gauge of most recent duration

2. In-process call ledger (`recent_calls(limit=100)`):
   Append-only ring of `LLMCallRecord` entries — useful for cockpit panels
   and per-mission cost attribution.

Why a separate module
---------------------
The W5.1 prom layer is generic; the LLM call surface has unique field
semantics (input vs output tokens, cost estimate, blocked-by-SAIb paths)
that would clutter the prom registry if we tried to model them inline.

Cost estimation
---------------
A coarse per-model token rate table (USD per 1k tokens) lets us emit a
`aos_llm_cost_usd_total` counter. The numbers are *posted public list
prices* and are best-effort — the table is overridable via
`AOS_LLM_PRICING` (JSON env var) for callers who want exact cost.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Optional

from src.core.observability.prom import Gauge, LabeledCounter

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pricing table (USD per 1k tokens). List prices as of Q2 2026.
# ---------------------------------------------------------------------------

_DEFAULT_PRICING: dict[str, dict[str, float]] = {
    # Claude 4.x family — actual numbers should be sourced from billing.
    "claude-opus-4-7":       {"input": 0.015,  "output": 0.075},
    "claude-sonnet-4-6":     {"input": 0.003,  "output": 0.015},
    "claude-haiku-4-5":      {"input": 0.001,  "output": 0.005},
    # Wildcard fallback for unknown models.
    "_default":              {"input": 0.003,  "output": 0.015},
}


def _load_pricing() -> dict[str, dict[str, float]]:
    """Resolve the active pricing table. Operator-overridable via env."""
    raw = (os.environ.get("AOS_LLM_PRICING", "") or "").strip()
    if not raw:
        return _DEFAULT_PRICING
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("expected JSON object")
        return {**_DEFAULT_PRICING, **parsed}
    except Exception as exc:
        _log.warning("AOS_LLM_PRICING invalid (%s); using defaults", exc)
        return _DEFAULT_PRICING


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = _load_pricing()
    rates = pricing.get(model, pricing["_default"])
    return (
        (input_tokens / 1000.0) * rates.get("input", 0.0)
        + (output_tokens / 1000.0) * rates.get("output", 0.0)
    )


# ---------------------------------------------------------------------------
# Counters + gauge
# ---------------------------------------------------------------------------

llm_calls_total = LabeledCounter(
    "aos_llm_calls_total",
    "LLM gateway invocations labeled by model, via (adapter), and outcome.",
)
llm_tokens_total = LabeledCounter(
    "aos_llm_tokens_total",
    "Tokens consumed by direction (input/output) per model.",
)
llm_call_seconds_total = LabeledCounter(
    "aos_llm_call_seconds_total",
    "Cumulative wall-clock seconds spent in LLM calls per model+via.",
)
llm_cost_usd_total = LabeledCounter(
    "aos_llm_cost_usd_total",
    "Estimated cumulative LLM cost in USD per model+via.",
)
llm_last_call_seconds = Gauge(
    "aos_llm_last_call_seconds",
    "Duration of the most recent LLM call (seconds) per model+via.",
)


# ---------------------------------------------------------------------------
# Per-call ledger
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LLMCallRecord:
    timestamp:     datetime
    model:         str
    via:           str
    status:        str           # "ok" | "error" | "blocked" | "unavailable"
    duration_s:    float
    input_tokens:  int           = 0
    output_tokens: int           = 0
    cost_usd:      float         = 0.0
    error_class:   Optional[str] = None


_LEDGER_LIMIT = 1000
_ledger: Deque[LLMCallRecord] = deque(maxlen=_LEDGER_LIMIT)
_ledger_lock = threading.Lock()


def recent_calls(limit: int = 100) -> list[LLMCallRecord]:
    """Return up to *limit* most-recent LLM calls, newest first."""
    with _ledger_lock:
        items = list(_ledger)
    return list(reversed(items))[:limit]


def reset_ledger_for_tests() -> None:
    """Test hook — clears the ledger (counters reset via prom.reset_all_for_tests)."""
    with _ledger_lock:
        _ledger.clear()


# ---------------------------------------------------------------------------
# Emission API — called by the LLMGateway wrapper
# ---------------------------------------------------------------------------

def record_call(
    *,
    model: str,
    via: str,
    status: str,
    duration_s: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error_class: Optional[str] = None,
) -> None:
    """Append a call record + emit Prometheus counters.

    All arguments are required by name to make accidental position errors
    impossible. Never raises — telemetry failures must not break LLM calls.
    """
    try:
        labels_call = {"model": model, "via": via, "status": status}
        llm_calls_total.inc(labels=labels_call)
        llm_call_seconds_total.inc(by=duration_s, labels={"model": model, "via": via})
        llm_last_call_seconds.set(duration_s, labels={"model": model, "via": via})
        if input_tokens:
            llm_tokens_total.inc(
                by=input_tokens,
                labels={"model": model, "direction": "input"},
            )
        if output_tokens:
            llm_tokens_total.inc(
                by=output_tokens,
                labels={"model": model, "direction": "output"},
            )
        cost = estimate_cost_usd(model, input_tokens, output_tokens)
        if cost > 0:
            llm_cost_usd_total.inc(
                by=cost,
                labels={"model": model, "via": via},
            )
        rec = LLMCallRecord(
            timestamp=datetime.now(timezone.utc),
            model=model,
            via=via,
            status=status,
            duration_s=duration_s,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            error_class=error_class,
        )
        with _ledger_lock:
            _ledger.append(rec)
    except Exception as exc:  # pragma: no cover — best-effort
        _log.warning("llm_telemetry: emission failed: %s", exc)
