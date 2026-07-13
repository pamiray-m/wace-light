"""
W6.4 — Anthropic Batch API client + opt-in queue.

Anthropic's Message Batches API (POST /v1/messages/batches) offers a 50%
discount on input and output tokens, with results returned within 24 hours.
For non-urgent async reasoning — e.g. Board ADVISORY consultations that
don't block a pipeline, mission L1 feedback processing, archival
classification — that discount is a direct GM lever.

What this module does (minimum viable W6.4)
-------------------------------------------
1. `BatchRequest` (frozen) — one prompt in a batch. Carries the same kwargs
   we'd pass to LLMGateway.complete plus a caller-supplied `custom_id` so
   results can be reconciled.
2. `BatchClient` — HTTP wrapper for /v1/messages/batches. `submit`, `status`,
   `results`. Never raises on transient failures — operators get a result
   object with `error` set.
3. `BatchQueue` singleton (`batch_queue`) — in-memory append-only queue of
   pending BatchRequests. Callers append via `enqueue()`; an operator
   process calls `flush_to_client(client, model)` at a cadence convenient
   for them (e.g. every 6h via cron).

Not in this packet (deferred)
-----------------------------
- Periodic flush loop in the FastAPI lifespan. The cron timing is a deploy
  decision; we ship the capability without the schedule.
- Persistent queue. The current queue is in-memory; restarts drop pending
  work. For production we'd need a DB-backed queue + idempotent flush.

Wire-level shape (per Anthropic docs)
-------------------------------------
POST /v1/messages/batches
Body:
{
  "requests": [
    {
      "custom_id": "<caller-supplied stable id>",
      "params": {
        "model": "...",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "..."}],
        "system": "..."
      }
    },
    ...
  ]
}
Returns: {"id": "msgbatch_...", "processing_status": "in_progress", ...}
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.observability.prom import LabeledCounter

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

batch_ops_total = LabeledCounter(
    "aos_llm_batch_ops_total",
    "Anthropic Batch API operations by op (enqueue/submit/poll/results) + status.",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BatchRequest:
    custom_id:  str
    prompt:     str
    system:     str = ""
    max_tokens: int = 1024
    # The model is set at flush time (the entire batch goes to one model).


@dataclass(frozen=True)
class BatchSubmissionResult:
    batch_id:           Optional[str]
    submitted_count:    int
    processing_status:  Optional[str] = None
    error:              Optional[str] = None
    submitted_at:       datetime      = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# In-memory queue
# ---------------------------------------------------------------------------

class BatchQueue:
    """Thread-safe append-only queue of pending BatchRequests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: list[BatchRequest] = []

    def enqueue(self, request: BatchRequest) -> None:
        with self._lock:
            self._pending.append(request)
        batch_ops_total.inc(labels={"op": "enqueue", "status": "ok"})

    def size(self) -> int:
        with self._lock:
            return len(self._pending)

    def peek(self) -> list[BatchRequest]:
        with self._lock:
            return list(self._pending)

    def drain(self) -> list[BatchRequest]:
        """Atomically pop ALL pending requests and return them."""
        with self._lock:
            items, self._pending = self._pending, []
        return items

    def reset_for_tests(self) -> None:
        with self._lock:
            self._pending.clear()


batch_queue = BatchQueue()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class BatchClient:
    """Minimal HTTP wrapper for Anthropic's /v1/messages/batches endpoint.

    Uses httpx (already a dependency via the gateway's HTTPX fallback). Never
    raises — failures return a `BatchSubmissionResult` with `error` set.
    """

    _DEFAULT_URL = "https://api.anthropic.com/v1/messages/batches"
    _ANTHROPIC_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = (api_key or os.environ.get("ANTHROPIC_API_KEY", "")).strip()
        self._url     = url or self._DEFAULT_URL
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def submit(
        self,
        requests: list[BatchRequest],
        model:    str,
    ) -> BatchSubmissionResult:
        if not requests:
            return BatchSubmissionResult(
                batch_id=None, submitted_count=0, error="no requests to submit",
            )
        if not self._api_key:
            batch_ops_total.inc(labels={"op": "submit", "status": "no_key"})
            return BatchSubmissionResult(
                batch_id=None, submitted_count=len(requests),
                error="ANTHROPIC_API_KEY not set",
            )

        body = self._encode_body(requests, model)
        try:
            import httpx  # type: ignore[import]
            resp = httpx.post(
                self._url,
                headers={
                    "x-api-key":         self._api_key,
                    "anthropic-version": self._ANTHROPIC_VERSION,
                    "content-type":      "application/json",
                },
                json=body,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            _log.warning("BatchClient.submit failed: %s", exc)
            batch_ops_total.inc(labels={"op": "submit", "status": "error"})
            return BatchSubmissionResult(
                batch_id=None, submitted_count=len(requests), error=str(exc),
            )

        batch_id = data.get("id")
        processing_status = data.get("processing_status")
        batch_ops_total.inc(labels={"op": "submit", "status": "ok"})
        return BatchSubmissionResult(
            batch_id=batch_id,
            submitted_count=len(requests),
            processing_status=processing_status,
        )

    def status(self, batch_id: str) -> dict[str, Any]:
        if not self._api_key:
            return {"error": "ANTHROPIC_API_KEY not set"}
        try:
            import httpx
            resp = httpx.get(
                f"{self._url}/{batch_id}",
                headers={
                    "x-api-key":         self._api_key,
                    "anthropic-version": self._ANTHROPIC_VERSION,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            batch_ops_total.inc(labels={"op": "poll", "status": "ok"})
            return resp.json()
        except Exception as exc:
            _log.warning("BatchClient.status failed: %s", exc)
            batch_ops_total.inc(labels={"op": "poll", "status": "error"})
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Body encoding
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_body(requests: list[BatchRequest], model: str) -> dict:
        return {
            "requests": [
                {
                    "custom_id": r.custom_id,
                    "params": {
                        "model":      model,
                        "max_tokens": r.max_tokens,
                        "messages": [{"role": "user", "content": r.prompt}],
                        **({"system": r.system} if r.system else {}),
                    },
                }
                for r in requests
            ]
        }


# ---------------------------------------------------------------------------
# Convenience: flush the queue
# ---------------------------------------------------------------------------

def flush_to_client(
    client: BatchClient,
    model:  str,
) -> BatchSubmissionResult:
    """Drain the queue and submit everything in one batch."""
    pending = batch_queue.drain()
    return client.submit(pending, model=model)
