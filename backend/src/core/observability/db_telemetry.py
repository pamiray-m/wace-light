"""
W5.4 — DB query telemetry.

Hooks every SQLAlchemy `Engine` via global event listeners so each query is
timed and classified. Slow queries (above `AOS_DB_SLOW_QUERY_THRESHOLD_MS`,
default 250ms) are appended to a per-process ring buffer for cockpit
inspection AND logged at WARNING.

Prom series
-----------
aos_db_queries_total{kind}              — query counts by leading keyword
aos_db_query_seconds_total{kind}        — cumulative wall-clock by kind
aos_db_slow_queries_total{kind}         — slow-query count by kind
aos_db_last_query_seconds{kind}         — most recent query duration (gauge)

Statement classification
------------------------
We extract the leading SQL verb (SELECT / INSERT / UPDATE / DELETE / DDL /
TX / OTHER). The raw statement text is NOT exported in metrics — only the
verb. The ring buffer stores a 200-char prefix so operators can debug
without putting full statements (and potentially PII parameter values)
into long-lived telemetry storage.

Why a listener instead of middleware
------------------------------------
HTTP middleware can't see queries triggered from background loops (W4.1,
W4.2, W4.3, W4.6) or from the scheduler. SQLAlchemy's Engine-level event
hook catches every query regardless of caller.

Auto-registration
-----------------
This module attaches its listeners at import time via the
`@event.listens_for(Engine, ...)` decorators. Importing the module is
sufficient — there is no public install function to forget to call. The
DB layer (`src.core.registry.database`) imports this module on its own
load so every Engine gets the hooks "for free".
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine

from src.core.observability.prom import Gauge, LabeledCounter

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Counters + gauge
# ---------------------------------------------------------------------------

db_queries_total = LabeledCounter(
    "aos_db_queries_total",
    "DB query count by leading SQL verb (kind).",
)
db_query_seconds_total = LabeledCounter(
    "aos_db_query_seconds_total",
    "Cumulative wall-clock seconds spent executing DB queries by kind.",
)
db_slow_queries_total = LabeledCounter(
    "aos_db_slow_queries_total",
    "Queries exceeding the slow-query threshold by kind.",
)
db_last_query_seconds = Gauge(
    "aos_db_last_query_seconds",
    "Duration of the most recent DB query (seconds) by kind.",
)


# ---------------------------------------------------------------------------
# Slow-query ring
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SlowQueryRecord:
    timestamp:  datetime
    kind:       str
    duration_s: float
    statement_preview: str   # first 200 chars, no parameters


_RING_LIMIT = 200
_ring: Deque[SlowQueryRecord] = deque(maxlen=_RING_LIMIT)
_ring_lock = threading.Lock()


def recent_slow_queries(limit: int = 50) -> list[SlowQueryRecord]:
    with _ring_lock:
        items = list(_ring)
    return list(reversed(items))[:limit]


def reset_db_telemetry_for_tests() -> None:
    """Test hook — clears the slow-query ring (counters reset via prom)."""
    with _ring_lock:
        _ring.clear()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLD_MS = 250


def slow_threshold_seconds() -> float:
    raw = (os.environ.get("AOS_DB_SLOW_QUERY_THRESHOLD_MS", "") or "").strip()
    if not raw:
        return _DEFAULT_THRESHOLD_MS / 1000.0
    try:
        ms = int(raw)
        return (ms if ms > 0 else _DEFAULT_THRESHOLD_MS) / 1000.0
    except (TypeError, ValueError):
        return _DEFAULT_THRESHOLD_MS / 1000.0


def is_enabled() -> bool:
    """Operator kill switch. Default ON; set AOS_DB_TELEMETRY=off to disable."""
    raw = (os.environ.get("AOS_DB_TELEMETRY", "on") or "on").strip().lower()
    return raw not in ("off", "0", "false", "no")


# ---------------------------------------------------------------------------
# Statement classification
# ---------------------------------------------------------------------------

_DDL_KEYWORDS = frozenset({"CREATE", "ALTER", "DROP", "TRUNCATE"})
_TX_KEYWORDS  = frozenset({"BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE"})
_DML_KEYWORDS = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})

_VERB_RE = re.compile(r"^\s*(--[^\n]*\n)*\s*([A-Z]+)", re.IGNORECASE)


def classify_statement(statement: str) -> str:
    """Return the leading SQL verb in uppercase, or 'OTHER'."""
    if not statement:
        return "OTHER"
    m = _VERB_RE.match(statement)
    if not m:
        return "OTHER"
    verb = m.group(2).upper()
    if verb in _DML_KEYWORDS:
        return verb
    if verb in _DDL_KEYWORDS:
        return "DDL"
    if verb in _TX_KEYWORDS:
        return "TX"
    return "OTHER"


def _statement_preview(statement: str) -> str:
    """First 200 chars of the *raw* statement (no parameter substitution)."""
    if not statement:
        return ""
    s = " ".join(statement.split())
    return s[:200]


# ---------------------------------------------------------------------------
# Listener emission
# ---------------------------------------------------------------------------

def _record_query(kind: str, duration_s: float, statement: str) -> None:
    """Append telemetry for a completed query. Never raises."""
    try:
        labels = {"kind": kind}
        db_queries_total.inc(labels=labels)
        db_query_seconds_total.inc(by=duration_s, labels=labels)
        db_last_query_seconds.set(duration_s, labels=labels)

        if duration_s >= slow_threshold_seconds():
            db_slow_queries_total.inc(labels=labels)
            rec = SlowQueryRecord(
                timestamp=datetime.now(timezone.utc),
                kind=kind,
                duration_s=duration_s,
                statement_preview=_statement_preview(statement),
            )
            with _ring_lock:
                _ring.append(rec)
            _log.warning(
                "db slow query kind=%s duration=%.3fs preview=%r",
                kind, duration_s, rec.statement_preview,
            )
    except Exception:  # pragma: no cover — telemetry must never break the query
        pass


# ---------------------------------------------------------------------------
# Listener registration — runs at import time
# ---------------------------------------------------------------------------

_INFO_KEY = "_aos_db_t0"


@event.listens_for(Engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    if not is_enabled():
        return
    # context can be None for some dialects/cursors; guard.
    if context is not None:
        context._aos_db_t0 = time.monotonic()  # type: ignore[attr-defined]


@event.listens_for(Engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    if not is_enabled():
        return
    t0 = getattr(context, "_aos_db_t0", None) if context is not None else None
    if t0 is None:
        return
    duration = time.monotonic() - t0
    kind = classify_statement(statement)
    _record_query(kind, duration, statement)
