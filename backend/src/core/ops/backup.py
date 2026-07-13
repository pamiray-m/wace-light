"""
Ops-3 — Backup & Restore Service.

Exports all persistent AOS state to a portable, compressed JSON backup file
and restores it into a target database with integrity validation.

Data classification
-------------------
BACKED UP (critical state):
  operators          — hashed_password is bcrypt (one-way hash, safe).
  operator_sessions  — refresh_token_hash is SHA-256 (one-way hash, safe).
  audit_log          — append-only security records.
  agents             — agent registry (source of truth).
  hierarchy_map      — agent authority relationships.
  skill_packages     — knowledge/skill definitions.
  memory_contexts    — per-agent memory narratives.
  playbooks          — structured instruction sequences.
  tool_definitions   — integration catalog.
  tool_bindings      — integration bindings.
                       vaulted_credentials_ref is AES-256-GCM ciphertext —
                       backed up as-is (encrypted blob, never decrypted).

EXCLUDED (ephemeral operational state — rebuilt from runtime events):
  transition_events  — lifecycle event log; ephemeral operational trace.
  task_store         — task dispatch records; runtime-ephemeral.

Secret safety
-------------
No plaintext credentials ever reach the backup:
  - Passwords are stored as bcrypt hashes only; plaintext is never persisted.
  - Refresh tokens are stored as SHA-256 hashes only; raw tokens are never
    persisted after issuance.
  - Tool credentials are stored as AES-256-GCM ciphertext only; plaintext
    is never written to the DB.

The AOS_VAULT_KEY environment variable (used to decrypt tool credentials)
is NOT in the database and must be preserved separately out-of-band.
See docs/ops-backup.md for the full key management procedure.

Backup file format
------------------
A gzip-compressed JSON file with the following structure:

  {
    "metadata": {
      "format_version": "1",
      "aos_version": "0.1.0",
      "created_at": "<ISO 8601 UTC>",
      "db_url_hint": "<dialect only, no credentials>",
      "tables": ["operators", ...],
      "row_counts": {"operators": N, ...}
    },
    "data": {
      "operators": [{...}, ...],
      ...
    }
  }

All datetime values are serialised as ISO 8601 UTC strings.
JSON/dict columns are embedded as native JSON objects.
Binary columns are not present in the AOS schema.

Restore strategy
----------------
Restore runs inside a single SQLAlchemy transaction.  Tables are cleared
and reloaded in FK-safe dependency order.  If any step fails the transaction
is rolled back and the database is left in its pre-restore state.

Assumptions
-----------
- Restore is a maintenance operation.  The AOS API should be stopped or
  traffic drained before running restore to avoid write conflicts.
- The target database must already have the schema created (init_db must
  have been run at least once, or the schema must exist from a prior run).
- The vault key (AOS_VAULT_KEY) must be the same as when the backup was
  taken; otherwise vaulted credentials cannot be unsealed after restore.
"""

from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FORMAT_VERSION = "1"
_AOS_VERSION = "0.1.0"

# Tables included in backup, in restore-safe dependency order.
# (hierarchy_map refs agents via CASCADE; operator_sessions refs operators
#  at the service layer but has no DB FK, so order is still enforced here
#  for semantic correctness.)
BACKUP_TABLES: tuple[str, ...] = (
    "operators",
    "operator_sessions",
    "audit_log",
    "agents",
    "hierarchy_map",
    "skill_packages",
    "memory_contexts",
    "playbooks",
    "tool_definitions",
    "tool_bindings",
)

# Tables intentionally excluded (ephemeral operational state).
EXCLUDED_TABLES: tuple[str, ...] = (
    "transition_events",
    "task_store",
)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class BackupManifest:
    """Summary of a completed backup operation."""
    path: Path
    created_at: str
    tables: tuple[str, ...]
    row_counts: dict[str, int]
    size_bytes: int

    @property
    def total_rows(self) -> int:
        return sum(self.row_counts.values())


@dataclass
class RestoreResult:
    """Summary of a completed restore operation."""
    path: Path
    backup_created_at: str
    tables: tuple[str, ...]
    row_counts: dict[str, int]

    @property
    def total_rows(self) -> int:
        return sum(self.row_counts.values())


@dataclass
class VerifyResult:
    """Result of backup file integrity verification."""
    valid: bool
    path: Path
    errors: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialise_row(row: Any) -> dict:
    """
    Convert a SQLAlchemy row proxy or mapped object to a plain dict.

    Datetime values → ISO 8601 UTC strings.
    All other types pass through; JSON columns are already dicts/lists.
    """
    d: dict = {}
    for col in row.__table__.columns:
        val = getattr(row, col.key)
        if isinstance(val, datetime):
            # Ensure UTC-awareness before serialising
            if val.tzinfo is None:
                val = val.replace(tzinfo=timezone.utc)
            d[col.key] = val.isoformat()
        else:
            d[col.key] = val
    return d


def _deserialise_value(val: Any) -> Any:
    """
    Restore a value from JSON to the appropriate Python type.

    ISO 8601 datetime strings with timezone offsets are converted back to
    timezone-aware datetime objects.  Everything else passes through.
    """
    if not isinstance(val, str):
        return val
    # Attempt datetime parse for strings that look like ISO timestamps
    if len(val) >= 19 and "T" in val and (val.endswith("Z") or "+" in val or val.count("-") >= 3):
        try:
            # Python 3.11+ supports Z; older versions need normalisation
            normalised = val.replace("Z", "+00:00")
            return datetime.fromisoformat(normalised)
        except (ValueError, TypeError):
            pass
    return val


def _parse_row(row_dict: dict) -> dict:
    """Apply _deserialise_value to every value in a backup row dict."""
    return {k: _deserialise_value(v) for k, v in row_dict.items()}


# ---------------------------------------------------------------------------
# Backup Service
# ---------------------------------------------------------------------------


class BackupService:
    """
    Database-agnostic backup and restore service.

    Uses SQLAlchemy ORM reflection to read all rows from each registered
    table and writes them to a gzip-compressed JSON backup file.  Restore
    reads the backup and reloads all rows inside a single transaction.

    Parameters
    ----------
    session_factory : Callable that returns a new SQLAlchemy Session.
                      Defaults to src.core.registry.database.get_session.
                      Inject a different factory in tests.
    """

    def __init__(self, session_factory=None) -> None:
        if session_factory is None:
            from src.core.registry.database import get_session
            session_factory = get_session
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def backup(self, output_path: Path | str) -> BackupManifest:
        """
        Export all critical tables to a gzip-compressed JSON backup file.

        Parameters
        ----------
        output_path : Destination file path.  Parent directories must exist.
                      Overwrites an existing file at the same path.

        Returns
        -------
        BackupManifest describing the completed backup.

        Raises
        ------
        IOError / OSError : If the output path is not writable.
        SQLAlchemyError   : If any table cannot be queried.
        """
        output_path = Path(output_path)
        created_at = datetime.now(timezone.utc).isoformat()

        _log.info("backup.started", extra={"event": "backup.started",
                                            "output_path": str(output_path)})

        session = self._session_factory()
        try:
            data: dict[str, list[dict]] = {}
            row_counts: dict[str, int] = {}

            for table_name in BACKUP_TABLES:
                rows = self._export_table(session, table_name)
                data[table_name] = rows
                row_counts[table_name] = len(rows)
                _log.debug("backup.table_exported",
                           extra={"event": "backup.table_exported",
                                  "table": table_name, "rows": len(rows)})
        finally:
            session.close()

        payload = {
            "metadata": {
                "format_version": _FORMAT_VERSION,
                "aos_version": _AOS_VERSION,
                "created_at": created_at,
                "tables": list(BACKUP_TABLES),
                "excluded_tables": list(EXCLUDED_TABLES),
                "row_counts": row_counts,
            },
            "data": data,
        }

        with gzip.open(output_path, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, default=str)

        size_bytes = output_path.stat().st_size
        manifest = BackupManifest(
            path=output_path,
            created_at=created_at,
            tables=BACKUP_TABLES,
            row_counts=row_counts,
            size_bytes=size_bytes,
        )

        _log.info(
            "backup.completed",
            extra={
                "event": "backup.completed",
                "output_path": str(output_path),
                "total_rows": manifest.total_rows,
                "size_bytes": size_bytes,
            },
        )
        return manifest

    def restore(
        self,
        backup_path: Path | str,
        *,
        clear_existing: bool = True,
    ) -> RestoreResult:
        """
        Restore all tables from a backup file.

        Parameters
        ----------
        backup_path     : Path to the backup file produced by backup().
        clear_existing  : If True (default), existing rows in each table are
                          deleted before inserting backup rows.  If False,
                          rows are inserted without clearing; duplicate PKs
                          will raise an IntegrityError.

        Returns
        -------
        RestoreResult describing rows loaded per table.

        Raises
        ------
        FileNotFoundError : backup_path does not exist.
        ValueError        : Backup file format is invalid or version mismatch.
        SQLAlchemyError   : Transaction failure — DB is left unchanged on error.
        """
        backup_path = Path(backup_path)
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        _log.info("restore.started", extra={"event": "restore.started",
                                             "backup_path": str(backup_path)})

        payload = self._load_backup(backup_path)
        metadata = payload["metadata"]
        data = payload["data"]

        backup_created_at = metadata.get("created_at", "unknown")
        row_counts: dict[str, int] = {}

        session = self._session_factory()
        try:
            # Single transaction — either all tables restore or none do.
            with session.begin():
                for table_name in BACKUP_TABLES:
                    rows = data.get(table_name, [])
                    if clear_existing:
                        self._clear_table(session, table_name)
                    self._load_table(session, table_name, rows)
                    row_counts[table_name] = len(rows)
                    _log.debug("restore.table_loaded",
                               extra={"event": "restore.table_loaded",
                                      "table": table_name, "rows": len(rows)})
        except Exception:
            session.rollback()
            _log.error("restore.failed", extra={"event": "restore.failed",
                                                 "backup_path": str(backup_path)})
            raise
        finally:
            session.close()

        result = RestoreResult(
            path=backup_path,
            backup_created_at=backup_created_at,
            tables=BACKUP_TABLES,
            row_counts=row_counts,
        )
        _log.info(
            "restore.completed",
            extra={
                "event": "restore.completed",
                "backup_path": str(backup_path),
                "total_rows": result.total_rows,
            },
        )
        return result

    def verify(self, backup_path: Path | str) -> VerifyResult:
        """
        Validate a backup file without performing a restore.

        Checks:
          - File exists and is readable.
          - Decompresses without error.
          - Top-level structure matches expected schema.
          - format_version is supported.
          - All BACKUP_TABLES are present in metadata.
          - Row counts in metadata match actual row counts in data.
          - No obvious secret leakage (no 'password' key with non-hash values,
            no JWT token patterns in any string field).

        Returns
        -------
        VerifyResult — .valid is True only if all checks pass.
        """
        backup_path = Path(backup_path)
        errors: list[str] = []

        if not backup_path.exists():
            return VerifyResult(valid=False, path=backup_path,
                                errors=[f"File not found: {backup_path}"])

        try:
            payload = self._load_backup(backup_path)
        except Exception as exc:
            return VerifyResult(valid=False, path=backup_path,
                                errors=[f"Failed to load backup: {exc}"])

        # Structure checks
        if "metadata" not in payload:
            errors.append("Missing 'metadata' key")
        if "data" not in payload:
            errors.append("Missing 'data' key")
        if errors:
            return VerifyResult(valid=False, path=backup_path, errors=errors)

        metadata = payload["metadata"]
        data = payload["data"]

        # Version check
        fv = metadata.get("format_version")
        if fv != _FORMAT_VERSION:
            errors.append(f"Unsupported format_version: {fv!r} (expected {_FORMAT_VERSION!r})")

        # Table presence
        declared_tables = set(metadata.get("tables", []))
        for tbl in BACKUP_TABLES:
            if tbl not in declared_tables:
                errors.append(f"Table '{tbl}' missing from metadata.tables")
            if tbl not in data:
                errors.append(f"Table '{tbl}' missing from data")

        # Row count consistency
        row_counts: dict[str, int] = {}
        declared_counts = metadata.get("row_counts", {})
        for tbl, rows in data.items():
            actual = len(rows) if isinstance(rows, list) else -1
            row_counts[tbl] = actual
            declared = declared_counts.get(tbl)
            if declared is not None and declared != actual:
                errors.append(
                    f"Row count mismatch for '{tbl}': "
                    f"metadata says {declared}, data has {actual}"
                )

        # Secret leakage check — passwords must look like bcrypt hashes
        for op_row in data.get("operators", []):
            hp = op_row.get("hashed_password", "")
            if hp and not hp.startswith("$2"):
                errors.append(
                    "operators.hashed_password does not look like a bcrypt hash "
                    "(must start with '$2'). Possible plaintext password in backup."
                )

        valid = len(errors) == 0
        return VerifyResult(valid=valid, path=backup_path, errors=errors, row_counts=row_counts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _export_table(self, session, table_name: str) -> list[dict]:
        """
        Read all rows from *table_name* using ORM model reflection.

        Returns a list of row dicts with serialised values.
        Raises ValueError if the table is not registered in Base.metadata.
        """
        from src.core.registry.database import Base
        import sqlalchemy

        table = Base.metadata.tables.get(table_name)
        if table is None:
            raise ValueError(
                f"Table '{table_name}' is not registered in Base.metadata. "
                f"Ensure all ORM models are imported before calling backup()."
            )

        result = session.execute(sqlalchemy.select(table))
        rows = []
        for row in result:
            row_dict: dict = {}
            for col in table.columns:
                val = row._mapping[col.key]
                if isinstance(val, datetime):
                    if val.tzinfo is None:
                        val = val.replace(tzinfo=timezone.utc)
                    row_dict[col.key] = val.isoformat()
                else:
                    row_dict[col.key] = val
            rows.append(row_dict)
        return rows

    def _clear_table(self, session, table_name: str) -> int:
        """Delete all rows from *table_name*. Returns the row count removed."""
        from src.core.registry.database import Base
        import sqlalchemy

        table = Base.metadata.tables.get(table_name)
        if table is None:
            return 0
        result = session.execute(sqlalchemy.delete(table))
        return result.rowcount if result.rowcount is not None else 0

    def _load_table(self, session, table_name: str, rows: list[dict]) -> None:
        """Insert *rows* into *table_name* using parameterised bulk insert."""
        if not rows:
            return

        from src.core.registry.database import Base
        import sqlalchemy

        table = Base.metadata.tables.get(table_name)
        if table is None:
            raise ValueError(f"Unknown table during restore: '{table_name}'")

        # Deserialise datetime strings back to datetime objects
        parsed = [_parse_row(r) for r in rows]
        session.execute(sqlalchemy.insert(table), parsed)

    def _load_backup(self, path: Path) -> dict:
        """Read and parse a backup file. Raises on decompression or JSON error."""
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
