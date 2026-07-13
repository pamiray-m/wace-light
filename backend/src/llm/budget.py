"""
W6.2 — Per-customer LLM budget caps.

Pairs with the W5.2 cost telemetry. Once we know the cost per LLM call, this
module decides whether the *next* call is allowed for a given customer_id.
The W4.x autonomous loops can pin a runaway customer's spend by setting a
daily / monthly USD ceiling and letting `BudgetTracker.check_or_raise()`
gate every LLM call attributed to that customer.

Surface
-------
- `BudgetCap` (frozen) — `daily_usd`, `monthly_usd`. -1 = unlimited.
- `BudgetState` (frozen) — `customer_id`, `daily_spent_usd`, `monthly_spent_usd`,
  `daily_cap_usd`, `monthly_cap_usd`, `state` ∈ {OK, WARN, EXHAUSTED}.
- `BudgetTracker` (singleton via `budget_tracker`) — in-memory accumulator.
  - `set_cap(customer_id, daily_usd, monthly_usd)` — override the default.
  - `record_cost(customer_id, usd)` — accrue.
  - `state(customer_id) -> BudgetState` — current standing.
  - `check_or_raise(customer_id)` — raise `LLMBudgetExceededError` if EXHAUSTED.

Defaults
--------
`AOS_LLM_BUDGET_DAILY_USD`    (default 10.0)
`AOS_LLM_BUDGET_MONTHLY_USD`  (default 200.0)
Per-customer overrides via `set_cap()` win over env defaults.
Set either env to a negative number to make the default unlimited.

Window semantics
----------------
- Daily window resets at 00:00 UTC.
- Monthly window resets at 00:00 UTC on day 1 of each calendar month.
- Windows are detected lazily at every `state()` / `record_cost()` call. No
  background sweep — state is computed from the cumulative bucket plus the
  window key.

Thresholds
----------
- OK        : daily_spent < 0.8 × daily_cap AND monthly_spent < 0.8 × monthly_cap
- WARN      : at least one of the two crossed 80% but neither crossed 100%
- EXHAUSTED : at least one of the two reached 100%

`-1` cap means unlimited — it never trips WARN or EXHAUSTED.

Telemetry
---------
- `aos_llm_budget_state{customer_id, state}` Gauge (1 = current state)
- `aos_llm_budget_blocks_total{customer_id}` Counter
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.core.observability.prom import Gauge, LabeledCounter

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class LLMBudgetExceededError(RuntimeError):
    """Raised when a customer's LLM budget cap is exhausted.

    The gateway catches this AFTER it's raised and lets it propagate — callers
    must handle the rejection (typically by routing to a cheaper model or
    surfacing the cap exhaustion to the operator).
    """
    def __init__(self, customer_id: str, state: "BudgetState") -> None:
        super().__init__(
            f"customer={customer_id!r} LLM budget exhausted "
            f"daily={state.daily_spent_usd:.4f}/{state.daily_cap_usd:.4f} "
            f"monthly={state.monthly_spent_usd:.4f}/{state.monthly_cap_usd:.4f}"
        )
        self.customer_id = customer_id
        self.state = state


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BudgetCap:
    daily_usd:   float
    monthly_usd: float


@dataclass(frozen=True)
class BudgetState:
    customer_id:       str
    daily_spent_usd:   float
    monthly_spent_usd: float
    daily_cap_usd:     float       # -1 means unlimited
    monthly_cap_usd:   float
    state:             str         # "OK" | "WARN" | "EXHAUSTED"


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

budget_state_gauge = Gauge(
    "aos_llm_budget_state",
    "Per-customer LLM budget state (1 = current). State ∈ OK/WARN/EXHAUSTED.",
)
budget_blocks_total = LabeledCounter(
    "aos_llm_budget_blocks_total",
    "LLM calls blocked because the customer's budget was exhausted.",
)


# ---------------------------------------------------------------------------
# Defaults from env
# ---------------------------------------------------------------------------

def _default_daily_cap() -> float:
    raw = (os.environ.get("AOS_LLM_BUDGET_DAILY_USD", "") or "").strip()
    if not raw:
        return 10.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 10.0


def _default_monthly_cap() -> float:
    raw = (os.environ.get("AOS_LLM_BUDGET_MONTHLY_USD", "") or "").strip()
    if not raw:
        return 200.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 200.0


# ---------------------------------------------------------------------------
# Window keys
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _daily_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _monthly_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------

class BudgetTracker:
    """In-memory per-customer cost accumulator with lazy window rollover."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # customer_id -> (daily_key, daily_spent, monthly_key, monthly_spent)
        self._spent: dict[str, tuple[str, float, str, float]] = {}
        # customer_id -> BudgetCap (override over env defaults)
        self._caps: dict[str, BudgetCap] = {}

    # ------------------------------------------------------------------
    # Cap management
    # ------------------------------------------------------------------

    def set_cap(self, customer_id: str, daily_usd: float, monthly_usd: float) -> None:
        with self._lock:
            self._caps[customer_id] = BudgetCap(
                daily_usd=daily_usd, monthly_usd=monthly_usd,
            )

    def get_cap(self, customer_id: str) -> BudgetCap:
        with self._lock:
            cap = self._caps.get(customer_id)
        if cap is not None:
            return cap
        return BudgetCap(
            daily_usd=_default_daily_cap(),
            monthly_usd=_default_monthly_cap(),
        )

    # ------------------------------------------------------------------
    # Accumulator
    # ------------------------------------------------------------------

    def _bucket_for(self, customer_id: str, now: datetime) -> tuple[float, float]:
        """Return (daily_spent, monthly_spent) for the CURRENT windows."""
        dk = _daily_key(now)
        mk = _monthly_key(now)
        with self._lock:
            entry = self._spent.get(customer_id)
            if entry is None:
                return 0.0, 0.0
            stored_dk, ds, stored_mk, ms = entry
            # Window rollover: reset the bucket that no longer matches today.
            if stored_dk != dk:
                ds = 0.0
            if stored_mk != mk:
                ms = 0.0
            return ds, ms

    def record_cost(self, customer_id: str, usd: float) -> BudgetState:
        """Accrue *usd* against *customer_id* and return the post-record state."""
        if usd < 0:
            usd = 0.0
        now = _now()
        dk = _daily_key(now)
        mk = _monthly_key(now)
        with self._lock:
            entry = self._spent.get(customer_id)
            if entry is None or entry[0] != dk:
                daily_spent = 0.0
            else:
                daily_spent = entry[1]
            if entry is None or entry[2] != mk:
                monthly_spent = 0.0
            else:
                monthly_spent = entry[3]
            daily_spent += usd
            monthly_spent += usd
            self._spent[customer_id] = (dk, daily_spent, mk, monthly_spent)
        return self._build_state(customer_id, daily_spent, monthly_spent)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def state(self, customer_id: str) -> BudgetState:
        ds, ms = self._bucket_for(customer_id, _now())
        return self._build_state(customer_id, ds, ms)

    def _build_state(
        self,
        customer_id: str,
        daily_spent: float,
        monthly_spent: float,
    ) -> BudgetState:
        cap = self.get_cap(customer_id)
        daily_cap = cap.daily_usd
        monthly_cap = cap.monthly_usd

        def _state_for() -> str:
            # Unlimited caps never trip WARN or EXHAUSTED.
            daily_pct = (daily_spent / daily_cap) if daily_cap > 0 else 0.0
            monthly_pct = (monthly_spent / monthly_cap) if monthly_cap > 0 else 0.0
            if (daily_cap > 0 and daily_pct >= 1.0) or (monthly_cap > 0 and monthly_pct >= 1.0):
                return "EXHAUSTED"
            if (daily_cap > 0 and daily_pct >= 0.8) or (monthly_cap > 0 and monthly_pct >= 0.8):
                return "WARN"
            return "OK"

        state_str = _state_for()
        result = BudgetState(
            customer_id=customer_id,
            daily_spent_usd=daily_spent,
            monthly_spent_usd=monthly_spent,
            daily_cap_usd=daily_cap,
            monthly_cap_usd=monthly_cap,
            state=state_str,
        )
        # Emit gauge — one row per (customer_id, state). Set 1 for the
        # current state and 0 for the others so the scrape always shows
        # exactly one active state per customer.
        try:
            for s in ("OK", "WARN", "EXHAUSTED"):
                budget_state_gauge.set(
                    1.0 if s == state_str else 0.0,
                    labels={"customer_id": customer_id, "state": s},
                )
        except Exception:  # pragma: no cover
            pass
        return result

    # ------------------------------------------------------------------
    # Guard
    # ------------------------------------------------------------------

    def check_or_raise(self, customer_id: str) -> BudgetState:
        """Raise `LLMBudgetExceededError` when the customer is EXHAUSTED.

        Otherwise return the current BudgetState. Callers that want non-
        raising semantics can use `state(customer_id)` instead.
        """
        st = self.state(customer_id)
        if st.state == "EXHAUSTED":
            try:
                budget_blocks_total.inc(labels={"customer_id": customer_id})
            except Exception:  # pragma: no cover
                pass
            raise LLMBudgetExceededError(customer_id, st)
        return st

    # ------------------------------------------------------------------
    # Reset for tests
    # ------------------------------------------------------------------

    def reset_for_tests(self) -> None:
        with self._lock:
            self._spent.clear()
            self._caps.clear()


# Process-level singleton.
budget_tracker = BudgetTracker()
