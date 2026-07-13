"""
OpenClaw connector configuration (Packet 5).

All settings are read from the central configuration module (src.config)
rather than os.environ directly.  This module is preserved for callers that
depend on the OpenClawSettings dataclass interface.

P2 note
-------
get_openclaw_settings() now delegates entirely to get_settings().openclaw
so that there is one canonical source of truth for environment variable reads.

Environment Variables (managed via src.config.loader)
-----------------------------------------------------
OPENCLAW_ENABLED         "true" / "1" / "yes" to activate the connector.
                         Any other value (or absent) → local_mock is used.

OPENCLAW_DEFAULT         "true" to make openclaw the default adapter instead of
                         local_mock.  Only meaningful when OPENCLAW_ENABLED=true.

OPENCLAW_BASE_URL        Base URL for the OpenClaw API endpoint.
                         Default: "stub://openclaw-local" (stub — no network call)

OPENCLAW_API_KEY         API key for authenticating with OpenClaw.
                         Default: "" (empty — stub ignores auth)

OPENCLAW_QUEUE_NAME      Default task queue name for job dispatch.
                         Default: "maib-tasks"

OPENCLAW_TIMEOUT_SECS    HTTP/SDK request timeout in seconds.
                         Default: 10

Security note
-------------
OPENCLAW_API_KEY must never be hardcoded.  The stub leaves it empty; production
deployments inject it via a secrets manager or CI/CD env injection.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpenClawSettings:
    """
    Immutable configuration snapshot for the OpenClaw connector.

    Constructed once at startup from the central config via
    ``get_openclaw_settings()``.  The frozen dataclass prevents accidental
    mutation during a request lifecycle.
    """

    enabled:      bool
    make_default: bool
    base_url:     str
    api_key:      str
    queue_name:   str
    timeout_secs: int


def get_openclaw_settings() -> OpenClawSettings:
    """
    Return OpenClaw configuration from the central config module.

    Delegates to get_settings().openclaw so that all environment variable
    reads are centralised in src.config.loader.  The returned object is safe
    to use even when no OPENCLAW_* variables are set — all fields have safe
    defaults that disable the connector.
    """
    from src.config import get_settings
    cfg = get_settings().openclaw
    return OpenClawSettings(
        enabled=cfg.enabled,
        make_default=cfg.make_default,
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        queue_name=cfg.queue_name,
        timeout_secs=cfg.timeout_secs,
    )
