"""
W5.1 — Prometheus-format metrics, zero-dependency.

We deliberately avoid `prometheus_client` so the metrics surface adds no new
runtime dependency. The format is simple text-line per sample, parseable by
every Prometheus scraper.

Primitives
----------
LabeledCounter — append-only counter with optional label dimensions. Calls
to `inc(labels={...})` index into a per-label-combination value. Thread-safe
via an internal lock.

Gauge — set/inc/dec primitive with the same label dimensions. Thread-safe.

Registry — module-level singleton owning every metric. `render_prom_text()`
walks the registry and produces a valid `text/plain; version=0.0.4` document.

Naming
------
All AOS metrics use the `aos_` prefix. Each labeled counter exposes one
HELP and one TYPE line, followed by N sample lines (one per label combo).

Example output
--------------
    # HELP aos_mission_submitted_total Mission submissions by source
    # TYPE aos_mission_submitted_total counter
    aos_mission_submitted_total{source="aa6_autonomous_loop"} 12
    aos_mission_submitted_total{source="user"} 3

    # HELP aos_autonomy_halted Autonomy halt state (1=halted, 0=running)
    # TYPE aos_autonomy_halted gauge
    aos_autonomy_halted{scope="global"} 0

Test isolation
--------------
Call `reset_all_for_tests()` between tests; metrics are process-singletons
and otherwise carry counter values across the suite.
"""
from __future__ import annotations

import threading
from typing import Iterable

# Lock guards the registry list and counter/gauge mutations alike.
_lock = threading.Lock()
_registry: list["_Metric"] = []


# ---------------------------------------------------------------------------
# Label key formatting
# ---------------------------------------------------------------------------

def _format_label_value(v: object) -> str:
    """Escape a label value per Prom text-format rules."""
    s = str(v)
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels_to_key(labels: dict[str, object] | None) -> tuple[tuple[str, str], ...]:
    """Canonicalize a labels dict to a hashable, sorted tuple."""
    if not labels:
        return ()
    return tuple(sorted((k, _format_label_value(v)) for k, v in labels.items()))


def _labels_to_inline(key: tuple[tuple[str, str], ...]) -> str:
    """Render a labels key as `{k1="v1",k2="v2"}` (empty string if no labels)."""
    if not key:
        return ""
    parts = ",".join(f'{k}="{v}"' for k, v in key)
    return "{" + parts + "}"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class _Metric:
    """Common base for LabeledCounter + Gauge."""
    _type: str  # "counter" or "gauge"

    def __init__(self, name: str, help_text: str) -> None:
        if not name or not name.startswith("aos_"):
            raise ValueError(f"metric names must start with 'aos_'; got {name!r}")
        self.name = name
        self.help_text = help_text
        self._values: dict[tuple[tuple[str, str], ...], float] = {}
        with _lock:
            _registry.append(self)

    def _samples(self) -> Iterable[tuple[tuple[tuple[str, str], ...], float]]:
        with _lock:
            return list(self._values.items())

    def render(self) -> str:
        """Render this metric as a Prom text-format block."""
        lines = [f"# HELP {self.name} {self.help_text}",
                 f"# TYPE {self.name} {self._type}"]
        samples = self._samples()
        if not samples:
            # Emit a no-label zero so scrapers see the series exists.
            lines.append(f"{self.name} 0")
        else:
            # Stable ordering — sorted by serialized label string.
            for key, value in sorted(samples, key=lambda kv: _labels_to_inline(kv[0])):
                v = int(value) if value.is_integer() else value
                lines.append(f"{self.name}{_labels_to_inline(key)} {v}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# LabeledCounter
# ---------------------------------------------------------------------------

class LabeledCounter(_Metric):
    """Append-only counter with optional label dimensions."""
    _type = "counter"

    def inc(self, by: float = 1.0, labels: dict[str, object] | None = None) -> None:
        if by < 0:
            raise ValueError("counters cannot decrement; got by={!r}".format(by))
        key = _labels_to_key(labels)
        with _lock:
            self._values[key] = self._values.get(key, 0.0) + by

    def value(self, labels: dict[str, object] | None = None) -> float:
        return self._values.get(_labels_to_key(labels), 0.0)


# ---------------------------------------------------------------------------
# Gauge
# ---------------------------------------------------------------------------

class Gauge(_Metric):
    """Set/inc/dec primitive with optional label dimensions."""
    _type = "gauge"

    def set(self, value: float, labels: dict[str, object] | None = None) -> None:
        key = _labels_to_key(labels)
        with _lock:
            self._values[key] = float(value)

    def inc(self, by: float = 1.0, labels: dict[str, object] | None = None) -> None:
        key = _labels_to_key(labels)
        with _lock:
            self._values[key] = self._values.get(key, 0.0) + by

    def dec(self, by: float = 1.0, labels: dict[str, object] | None = None) -> None:
        self.inc(-by, labels=labels)

    def value(self, labels: dict[str, object] | None = None) -> float:
        return self._values.get(_labels_to_key(labels), 0.0)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_prom_text() -> str:
    """Return the full registry rendered as Prom text-format."""
    with _lock:
        metrics = list(_registry)
    blocks = [m.render() for m in metrics]
    return "\n\n".join(blocks) + "\n"


def reset_all_for_tests() -> None:
    """Test hook — clear every counter/gauge value but keep the registry."""
    with _lock:
        for m in _registry:
            m._values.clear()


# ---------------------------------------------------------------------------
# AOS metric definitions
# ---------------------------------------------------------------------------
#
# Counters/gauges are defined here as module-level singletons; everything else
# in the codebase imports and increments them. Centralizing the definitions
# keeps the /metrics surface inspectable in one place.

# W4.1 — autonomous mission submission
mission_submitted_total = LabeledCounter(
    "aos_mission_submitted_total",
    "Mission submissions by source (e.g., aa6_autonomous_loop, user).",
)

# W4.2 — retry watchdog
retry_watchdog_retried_total = LabeledCounter(
    "aos_retry_watchdog_retried_total",
    "Missions auto-retried by the W4.2 watchdog.",
)
retry_watchdog_escalated_total = LabeledCounter(
    "aos_retry_watchdog_escalated_total",
    "Missions escalated to the Board after retry exhaustion.",
)

# W4.3 — proposal auto-apply
proposal_auto_apply_total = LabeledCounter(
    "aos_proposal_auto_apply_total",
    "L1 proposals auto-applied by type (behavioral_update, routing_optimization, ...).",
)

# W4.5 — autonomy gate
autonomy_halted = Gauge(
    "aos_autonomy_halted",
    "Autonomy halt state per scope (1=halted, 0=running).",
)

# W4.6 — playbooks
playbook_fired_total = LabeledCounter(
    "aos_playbook_fired_total",
    "Self-healing playbooks fired, labeled by rule_kind and action_type.",
)
