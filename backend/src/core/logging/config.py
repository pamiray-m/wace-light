"""
Ops-2 — Centralized logging configuration.

setup_logging() is the single entry point for configuring the AOS logging
stack.  It must be called once in the application lifespan before the first
log statement fires.

Design
------
- Delegates JSON formatting to the existing src.observability.logger
  infrastructure (JsonFormatter, configure_json_logging).
- Maps deployment environment → log level so that development emits DEBUG
  while production stays at WARNING, reducing log volume in prod.
- Idempotent: safe to call multiple times (configure_json_logging is a no-op
  if the handler is already installed).

Log level policy
----------------
  development : DEBUG  — full trace including vault/policy detail
  staging     : INFO   — normal operations, session events, readiness
  production  : WARNING — only anomalies, failures, denials

This is intentionally conservative for production: structured aggregators
like ELK/Datadog ingest WARNING+ by default; INFO/DEBUG can be re-enabled
by changing AOS_ENVIRONMENT without a code change.
"""

from __future__ import annotations

import logging

# Log levels by environment profile.
_LEVEL_MAP: dict[str, int] = {
    "development": logging.DEBUG,
    "staging":     logging.INFO,
    "production":  logging.WARNING,
}

_DEFAULT_LEVEL = logging.INFO


def get_log_level(environment: str) -> int:
    """
    Return the appropriate log level for *environment*.

    Falls back to INFO for unrecognised environment values so that a
    mis-spelled AOS_ENVIRONMENT does not silently suppress all logs.
    """
    return _LEVEL_MAP.get(environment, _DEFAULT_LEVEL)


def setup_logging(environment: str = "development", level: int | None = None) -> None:
    """
    Configure structured JSON logging for the AOS service.

    Parameters
    ----------
    environment : Deployment profile — "development" | "staging" | "production".
                  Determines the default log level if *level* is not given.
    level       : Explicit log level override.  Useful in tests.
                  If None, the level is derived from *environment*.

    Effects
    -------
    - Installs the AOS JsonFormatter on the root logger (idempotent).
    - Applies the resolved log level to the root logger.
    - Subsequent ``get_logger(__name__)`` calls return loggers that inherit
      the root level and emit JSON records.
    """
    from src.observability.logger import configure_json_logging

    resolved_level = level if level is not None else get_log_level(environment)
    configure_json_logging(level=resolved_level)
