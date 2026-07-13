"""
W3.5 — Unified audit export (HMAC-signed NDJSON).

Why this exists
---------------
The 2026-05-12 diligence flagged "No audit export / compliance reporting" as
a HIGH-severity enterprise procurement blocker:
  - Governance customer can query audit but no tamper-proof export
  - No immutable signatures
  - No SOC2-ready format

This module pulls records from the existing AA-5 and SAL-5 audit repositories,
filters by an ISO-8601 time range, serializes to newline-delimited JSON, and
returns the body + an HMAC-SHA256 signature an auditor can use to verify the
export was not modified post-download.

Why HMAC and not RSA/RFC-3161
-----------------------------
HMAC-SHA256 with a per-deployment secret is the minimum-viable SOC2-friendly
tamper evidence. Auditors who already trust the operator-held secret can
recompute the HMAC over the saved body and compare. A future packet can layer
RFC-3161 trusted-timestamping or detached RS256 signatures over the same
serialized body without changing the wire format — HMAC is the floor, not
the ceiling.

Configuration
-------------
AOS_AUDIT_HMAC_SECRET — required. Min 32 chars. SEPARATE from AOS_JWT_SECRET
                        so rotation policies differ (the JWT secret rotates
                        frequently; the audit HMAC secret is sealed at deploy
                        time and only rotated under controlled procedures).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Optional, Protocol, runtime_checkable

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AuditExportConfigError(RuntimeError):
    """Raised when AOS_AUDIT_HMAC_SECRET is unset or too short."""


# ---------------------------------------------------------------------------
# Record source Protocol — keeps the export decoupled from concrete repos
# ---------------------------------------------------------------------------

@runtime_checkable
class AuditRecordSource(Protocol):
    """
    Anything that yields audit records with a `.to_dict()` shape and a
    `.created_at` timestamp can plug in here. Lets tests inject lightweight
    fixtures and lets the export grow to new audit stores without touching
    this module's core logic.
    """
    def iter_records(self, since: Optional[datetime], until: Optional[datetime]) -> Iterator[dict[str, Any]]: ...

    @property
    def record_type(self) -> str: ...


class _AuditRepoSource:
    """
    Concrete source — wraps a list-returning audit repository. Each record
    is augmented with a `record_type` discriminator so a combined export
    file stays self-describing.
    """
    def __init__(
        self,
        record_type: str,
        list_fn,
        *,
        page_size: int = 500,
    ) -> None:
        self._record_type = record_type
        self._list_fn     = list_fn
        self._page_size   = page_size

    @property
    def record_type(self) -> str:
        return self._record_type

    def iter_records(
        self,
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> Iterator[dict[str, Any]]:
        """
        Page through the underlying repository's `list_*` method and emit
        records that fall within [since, until] (inclusive on both ends
        when set). Newest-first ordering is preserved from the repo.
        """
        offset = 0
        while True:
            page = self._list_fn(limit=self._page_size, offset=offset)
            if not page:
                return
            for rec in page:
                created = getattr(rec, "created_at", None)
                if since is not None and created is not None and created < since:
                    # Repos are newest-first → once we drop below `since` we can stop
                    return
                if until is not None and created is not None and created > until:
                    continue
                d = rec.to_dict()
                d["record_type"] = self._record_type
                yield d
            if len(page) < self._page_size:
                return
            offset += self._page_size


# ---------------------------------------------------------------------------
# Default-wired sources from AA-5 + SAL-5
# ---------------------------------------------------------------------------

def _default_sources() -> list[AuditRecordSource]:
    """
    Build the production source list — AA-5 auto-apply records, AA-5
    kill-switch records, and SAL-5 autonomy decisions.

    Failures to import a repo (e.g. during test isolation) leave the
    source out of the list rather than blowing up the whole export.
    """
    sources: list[AuditRecordSource] = []
    try:
        from src.api.routes.sal_auto_console import _DEFAULT_REPOSITORY as aa_repo
        sources.append(_AuditRepoSource("aa_apply",       aa_repo.list_auto_apply_records))
        sources.append(_AuditRepoSource("aa_kill_switch", aa_repo.list_kill_switch_records))
    except Exception as exc:
        _log.warning("audit export: AA-5 repo unavailable (%s) — skipping.", exc)
    try:
        # SAL-5 repo singleton location (mirrors AA-5's _DEFAULT_REPOSITORY).
        from src.api.routes.sal_console import _DEFAULT_REPOSITORY as sal_repo

        def _sal_list(*, limit: int, offset: int):
            # SAL repo list_all signature is `list_all(limit=N)` — no offset.
            # Page by re-slicing the head; auditors care about totals, not
            # window-walking perf at SAL scale.
            return sal_repo.list_all(limit=limit + offset)[offset:offset + limit]

        sources.append(_AuditRepoSource("sal_autonomy", _sal_list))
    except Exception as exc:
        _log.warning("audit export: SAL-5 repo unavailable (%s) — skipping.", exc)
    return sources


# ---------------------------------------------------------------------------
# HMAC secret management
# ---------------------------------------------------------------------------

_MIN_SECRET_LEN = 32


def _load_hmac_secret() -> bytes:
    """
    Resolve the audit HMAC secret. Required — never falls back to a default,
    never reuses the JWT secret.
    """
    raw = (os.environ.get("AOS_AUDIT_HMAC_SECRET", "") or "").strip()
    if not raw:
        raise AuditExportConfigError(
            "AOS_AUDIT_HMAC_SECRET is not set. Generate one with: "
            'python3 -c "import secrets; print(secrets.token_hex(32))"'
        )
    if len(raw) < _MIN_SECRET_LEN:
        raise AuditExportConfigError(
            f"AOS_AUDIT_HMAC_SECRET must be at least {_MIN_SECRET_LEN} chars "
            f"(currently {len(raw)})."
        )
    return raw.encode("utf-8")


# ---------------------------------------------------------------------------
# Export result
# ---------------------------------------------------------------------------

class AuditExportResult:
    """
    Held in memory for V1 — operator-scale exports are thousands of records,
    not millions. A future packet can switch to chunked-HMAC streaming for
    very large repos without changing the API shape (body bytes + signature).
    """
    __slots__ = ("body", "signature", "record_count", "exported_at", "since", "until")

    def __init__(
        self,
        body: bytes,
        signature: str,
        record_count: int,
        exported_at: datetime,
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> None:
        self.body         = body
        self.signature    = signature
        self.record_count = record_count
        self.exported_at  = exported_at
        self.since        = since
        self.until        = until

    def headers(self) -> dict[str, str]:
        """
        Build the HMAC-attestation response headers an auditor checks.

        Verification recipe (for an external auditor):
          recomputed = HMAC_SHA256(saved_body, AOS_AUDIT_HMAC_SECRET).hexdigest()
          assert recomputed == X-AOS-Audit-HMAC
        """
        h = {
            "X-AOS-Audit-HMAC":         self.signature,
            "X-AOS-Audit-Algorithm":    "HMAC-SHA256",
            "X-AOS-Audit-Record-Count": str(self.record_count),
            "X-AOS-Audit-Exported-At":  self.exported_at.isoformat(),
        }
        if self.since is not None:
            h["X-AOS-Audit-Since"] = self.since.isoformat()
        if self.until is not None:
            h["X-AOS-Audit-Until"] = self.until.isoformat()
        return h


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def export_audit(
    *,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    record_types: Optional[Iterable[str]] = None,
    sources: Optional[list[AuditRecordSource]] = None,
) -> AuditExportResult:
    """
    Build a tamper-evident audit export.

    Parameters
    ----------
    since        : Only include records with created_at >= since (inclusive).
    until        : Only include records with created_at <= until (inclusive).
    record_types : Only include sources whose record_type is in this set.
                   None means all configured sources.
    sources      : Inject specific sources (used by tests). When None, falls
                   back to the production AA-5 + SAL-5 sources.

    Returns
    -------
    AuditExportResult — body bytes (NDJSON, one record per line) + HMAC-SHA256
    signature + headers payload for the route layer.

    Raises
    ------
    AuditExportConfigError — when AOS_AUDIT_HMAC_SECRET is unset or too short.
    """
    secret = _load_hmac_secret()

    active_sources = sources if sources is not None else _default_sources()
    if record_types is not None:
        wanted = frozenset(record_types)
        active_sources = [s for s in active_sources if s.record_type in wanted]

    # ---- Stream records into a bytes buffer ----
    chunks: list[bytes] = []
    record_count = 0
    mac = hmac.new(secret, digestmod=hashlib.sha256)

    for source in active_sources:
        for rec in source.iter_records(since=since, until=until):
            line = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            chunks.append(line)
            mac.update(line)
            record_count += 1

    body = b"".join(chunks)
    signature = mac.hexdigest()
    exported_at = datetime.now(timezone.utc)

    _log.info(
        "audit export built record_count=%d since=%r until=%r exported_at=%r",
        record_count,
        since.isoformat() if since else None,
        until.isoformat() if until else None,
        exported_at.isoformat(),
    )

    return AuditExportResult(
        body=body,
        signature=signature,
        record_count=record_count,
        exported_at=exported_at,
        since=since,
        until=until,
    )


def verify_signature(body: bytes, signature_hex: str, secret: Optional[bytes] = None) -> bool:
    """
    External-auditor helper: re-compute HMAC over `body` and compare to the
    `X-AOS-Audit-HMAC` signature. Returns True iff bytes match (constant-time).
    Pass the secret explicitly when verifying outside the original deployment.
    """
    secret_bytes = secret if secret is not None else _load_hmac_secret()
    expected = hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_hex)
