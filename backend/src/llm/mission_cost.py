"""
W6.5 — Per-mission LLM cost tracker.

Pairs with the W5.2 telemetry + W6.2 budget caps. Where W5.2 tracks cost
globally by model and W6.2 enforces per-customer ceilings, this module
attributes every LLM call to a `mission_id` so operators can see exactly
which mission burned how much.

Why it's not a Prometheus label
-------------------------------
mission_id is high-cardinality (one per submitted mission). Putting it as
a Prom label would explode the scrape size and tank Prometheus performance.
Instead we keep an in-process ledger (`MissionCostTracker`) and expose it
via the mission console for operator queries. The W5.2 series stays at
model-level cardinality for /metrics scrapes.

Public surface
--------------
    from src.llm.mission_cost import mission_cost_tracker
    snapshot = mission_cost_tracker.get("mission-uuid-or-id")
    top = mission_cost_tracker.list_top_n(20)

Wired into `LLMGateway.complete(mission_id=...)` so any caller that wants
attribution just passes the kwarg.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Snapshot model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissionCostSnapshot:
    mission_id:        str
    total_usd:         float
    input_tokens:      int
    output_tokens:     int
    call_count:        int
    first_call_at:     datetime
    last_call_at:      datetime
    per_model_usd:     dict[str, float]
    per_model_tokens:  dict[str, dict[str, int]]   # model -> {input, output}


# ---------------------------------------------------------------------------
# Internal mutable bucket (not exposed; converted to snapshot on read)
# ---------------------------------------------------------------------------

@dataclass
class _Bucket:
    mission_id:       str
    total_usd:        float = 0.0
    input_tokens:     int   = 0
    output_tokens:    int   = 0
    call_count:       int   = 0
    first_call_at:    datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_call_at:     datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    per_model_usd:    dict[str, float]               = field(default_factory=dict)
    per_model_tokens: dict[str, dict[str, int]]      = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------

class MissionCostTracker:
    """In-memory per-mission LLM cost ledger. Thread-safe via a single lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}

    # ------------------------------------------------------------------
    # Mutate
    # ------------------------------------------------------------------

    def record(
        self,
        mission_id: str,
        *,
        model:         str,
        input_tokens:  int,
        output_tokens: int,
        cost_usd:      float,
    ) -> MissionCostSnapshot:
        if cost_usd < 0:
            cost_usd = 0.0
        if input_tokens < 0:
            input_tokens = 0
        if output_tokens < 0:
            output_tokens = 0
        now = datetime.now(timezone.utc)
        with self._lock:
            bucket = self._buckets.get(mission_id)
            if bucket is None:
                bucket = _Bucket(mission_id=mission_id, first_call_at=now, last_call_at=now)
                self._buckets[mission_id] = bucket
            bucket.total_usd      += cost_usd
            bucket.input_tokens   += input_tokens
            bucket.output_tokens  += output_tokens
            bucket.call_count     += 1
            bucket.last_call_at    = now
            bucket.per_model_usd[model] = bucket.per_model_usd.get(model, 0.0) + cost_usd
            mt = bucket.per_model_tokens.setdefault(model, {"input": 0, "output": 0})
            mt["input"]  += input_tokens
            mt["output"] += output_tokens
        return self._snapshot(bucket)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, mission_id: str) -> Optional[MissionCostSnapshot]:
        with self._lock:
            bucket = self._buckets.get(mission_id)
        if bucket is None:
            return None
        return self._snapshot(bucket)

    def list_top_n(self, n: int = 20) -> list[MissionCostSnapshot]:
        """Return up to *n* missions ordered by descending total cost."""
        if n <= 0:
            return []
        with self._lock:
            sorted_buckets = sorted(
                self._buckets.values(),
                key=lambda b: b.total_usd,
                reverse=True,
            )[:n]
        return [self._snapshot(b) for b in sorted_buckets]

    def list_all(self) -> list[MissionCostSnapshot]:
        with self._lock:
            buckets = list(self._buckets.values())
        return [self._snapshot(b) for b in buckets]

    # ------------------------------------------------------------------
    # Snapshot conversion (lock-free; called under lock OR with a copy)
    # ------------------------------------------------------------------

    @staticmethod
    def _snapshot(bucket: _Bucket) -> MissionCostSnapshot:
        return MissionCostSnapshot(
            mission_id=bucket.mission_id,
            total_usd=bucket.total_usd,
            input_tokens=bucket.input_tokens,
            output_tokens=bucket.output_tokens,
            call_count=bucket.call_count,
            first_call_at=bucket.first_call_at,
            last_call_at=bucket.last_call_at,
            per_model_usd=dict(bucket.per_model_usd),
            per_model_tokens={k: dict(v) for k, v in bucket.per_model_tokens.items()},
        )

    # ------------------------------------------------------------------
    # Test hook
    # ------------------------------------------------------------------

    def reset_for_tests(self) -> None:
        with self._lock:
            self._buckets.clear()


# Process-level singleton.
mission_cost_tracker = MissionCostTracker()
