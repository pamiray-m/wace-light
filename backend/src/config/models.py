"""
P2 — Configuration models.

Typed, immutable data containers for every configuration group consumed by
the AOS system.  Models are populated by the loader (src/config/loader.py)
and must never be constructed directly from ``os.environ`` in business code.

Groups
------
AuthConfig      JWT signing and token lifetime settings.
VaultConfig     AES-256-GCM credential vault key.
DatabaseConfig  SQLAlchemy connection string.
OperatorConfig  Seed operator credentials injected at startup.
OpenClawConfig  Optional OpenClaw runtime connector settings.
Settings        Top-level aggregate containing all groups.

Design notes
------------
- All models use ``frozen=True`` so the config object cannot be mutated
  after creation.  Configuration is read-only once loaded.
- Optional/defaulted fields use Python-native defaults; no field is
  silently None when a value was intended.
- No business logic lives here — models are pure data.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class AuthConfig(BaseModel):
    """JWT signing and token-lifetime configuration."""

    model_config = ConfigDict(frozen=True)

    jwt_secret: str = ""
    """HS256 signing secret. Required and minimum 32 characters in production."""

    jwt_algorithm: str = "HS256"
    """HMAC algorithm used to sign tokens. Fixed at HS256 for AOS v2."""

    jwt_expiry_minutes: int = 15
    """Access token lifetime in minutes. Defaults to 15 (short-lived; P4)."""

    refresh_expiry_days: int = 7
    """Refresh token lifetime in days. Defaults to 7. Set AOS_REFRESH_EXPIRY_DAYS."""


class VaultConfig(BaseModel):
    """AES-256-GCM credential vault configuration."""

    model_config = ConfigDict(frozen=True)

    vault_key: str = ""
    """
    Base64-encoded 32-byte AES-256 key.
    Required when the credential vault is used (not at startup if vault is
    unused).  An empty string means the vault is not configured.
    """


class DatabaseConfig(BaseModel):
    """Database connection configuration."""

    model_config = ConfigDict(frozen=True)

    url: str = "sqlite:///./aos_registry.db"
    """
    SQLAlchemy-compatible connection URL.
    Defaults to a local SQLite file for development.
    Set AOS_DB_URL to a PostgreSQL URL for production.
    """


class OperatorConfig(BaseModel):
    """Seed operator injected into the in-memory store at startup."""

    model_config = ConfigDict(frozen=True)

    username: str = "admin"
    """Operator username. Defaults to 'admin'."""

    password: str = ""
    """
    Plaintext password used to hash and seed the store.
    Required for login to succeed.  Empty means no seed operator is created.
    """

    role: str = "admin"
    """OperatorRole value: admin | viewer | auditor. Defaults to admin."""

    product_scope: str | None = None
    """Optional product scope restriction. None means unrestricted."""

    stream_scope: str | None = None
    """Optional stream scope restriction. None means unrestricted."""


class OpenClawConfig(BaseModel):
    """Optional OpenClaw runtime connector settings."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    """Activate the OpenClaw adapter. Defaults to False (local_mock used)."""

    make_default: bool = False
    """Promote OpenClaw to the default adapter when enabled. Defaults to False."""

    base_url: str = "stub://openclaw-local"
    """Base URL for the OpenClaw API endpoint."""

    api_key: str = ""
    """API key for authenticating with OpenClaw. Empty in stub/dev mode."""

    queue_name: str = "maib-tasks"
    """Default task queue name for job dispatch."""

    timeout_secs: int = 10
    """HTTP/SDK request timeout in seconds."""


class RateLimitConfig(BaseModel):
    """Per-bucket rate limit configuration for Ops-4 API protection."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    """Master switch. Set AOS_RATE_LIMIT_ENABLED=false to disable in dev/test."""

    # Auth endpoints — tightest limits (brute-force targets)
    auth_login_requests: int = 5
    """Max login attempts per IP per auth_login_window_seconds. Default 5."""
    auth_login_window_seconds: int = 60
    """Window duration for login rate limiting. Default 60 s."""

    auth_refresh_requests: int = 10
    """Max refresh attempts per IP per auth_refresh_window_seconds. Default 10."""
    auth_refresh_window_seconds: int = 60
    """Window duration for refresh rate limiting. Default 60 s."""

    auth_logout_requests: int = 20
    """Max logout attempts per IP per window. Default 20 (relaxed — logout must succeed)."""
    auth_logout_window_seconds: int = 60
    """Window duration for logout rate limiting. Default 60 s."""

    # Control endpoints (prompt / pause / resume / shutdown)
    control_requests: int = 30
    """Max control-plane commands per IP per control_window_seconds. Default 30."""
    control_window_seconds: int = 60
    """Window duration for control endpoint rate limiting. Default 60 s."""

    # Mutation endpoints (operator mgmt, skills, integrations write paths)
    mutation_requests: int = 20
    """Max mutation requests per IP per mutation_window_seconds. Default 20."""
    mutation_window_seconds: int = 60
    """Window duration for mutation endpoint rate limiting. Default 60 s."""

    # Mission/job status polling (designed to be called repeatedly)
    status_poll_requests: int = 300
    """Max status-poll requests per IP per status_poll_window_seconds. Default 300."""
    status_poll_window_seconds: int = 60
    """Window duration for status-poll rate limiting. Default 60 s."""

    # All other routes
    default_requests: int = 60
    """Max requests per IP per default_window_seconds for unlisted routes. Default 60."""
    default_window_seconds: int = 60
    """Window duration for default rate limiting. Default 60 s."""


class DAGConfig(BaseModel):
    """D2 — DAG Identity signing configuration."""

    model_config = ConfigDict(frozen=True)

    signing_key: str = ""
    """
    Hex-encoded HMAC-SHA256 signing secret used to sign DAG identity records.
    Must be at least 32 characters.  Set AOS_DAG_SIGNING_KEY in the environment.
    An empty string means no DAG identities can be signed (PENDING state only).
    """


class TrustInfluenceConfig(BaseModel):
    """L2 Activation — Oracle Trust Memory decision-influence configuration."""

    model_config = ConfigDict(frozen=True)

    influence_mode: Literal[
        "off", "advisory", "warn", "strict_deprecated", "strict_low_trust"
    ] = "advisory"
    """
    Progressive trust enforcement mode.

      off                — Trust memory ignored; current behavior fully preserved.
      advisory           — Trust profile returned; no blocking (DEFAULT).
      warn               — Emit warnings for low trust / deprecated; no blocking.
      strict_deprecated  — Block deprecated capabilities; warn on low trust.
      strict_low_trust   — Block deprecated and below-threshold capabilities.

    Set AOS_TRUST_INFLUENCE_MODE in the environment.
    """

    low_trust_threshold: float = 0.4
    """
    trust_score below this value is treated as "low trust".

    Must be in [0.0, 1.0].  Defaults to 0.4 (sits inside the warning band 0.3–0.6).
    Set AOS_TRUST_LOW_THRESHOLD in the environment.
    """

    critical_trust_threshold: float = 0.1
    """
    Optional critical-trust threshold reserved for future enforcement modes.

    Must be in [0.0, 1.0].  Defaults to 0.1.
    Set AOS_TRUST_CRITICAL_THRESHOLD in the environment.
    """


class LineageConfig(BaseModel):
    """L3 Activation — Decision lineage enforcement configuration."""

    model_config = ConfigDict(frozen=True)

    enforcement_mode: Literal["off", "warn", "strict_high_risk", "strict_all_material"] = "warn"
    """
    Progressive enforcement mode for L3 decision lineage.

      off                  — No enforcement; all actions proceed unconditionally.
      warn                 — Log a warning when lineage context is absent; action proceeds.
      strict_high_risk     — Block high-risk actions (GOVERNANCE_CHANGE,
                             CERTIFICATION_DECISION, CONTROL_PLANE_MUTATION) without lineage.
      strict_all_material  — Block any material action without lineage context.

    Set AOS_LINEAGE_ENFORCEMENT_MODE in the environment.
    Defaults to 'warn' so existing flows are never broken by activation.
    """


class RecoveryExecutionConfig(BaseModel):
    """L5 Activation — Controlled recovery execution configuration."""

    model_config = ConfigDict(frozen=True)

    execution_mode: Literal[
        "off", "advisory", "safe_execute", "controlled", "full"
    ] = "advisory"
    """
    Progressive recovery execution mode.

      off          — No plans executed; all calls return SKIPPED.
      advisory     — Evaluate guards; never execute state transitions (DEFAULT).
      safe_execute — Execute RETRY and RETRY_WITH_TIMEOUT_ADJUSTMENT only.
      controlled   — Execute RETRY, RETRY_WITH_TIMEOUT_ADJUSTMENT, COMPENSATE, ESCALATE.
      full         — Execute all strategies including ROLLBACK.

    Set AOS_RECOVERY_EXECUTION_MODE in the environment.
    Defaults to 'advisory' so existing recovery flows are never mutated by activation.
    """


class Settings(BaseModel):
    """
    Top-level AOS configuration aggregate.

    A single ``Settings`` instance is produced by ``get_settings()`` for each
    call (no global singleton) so that test fixtures can monkeypatch environment
    variables and receive fresh values without explicit cache invalidation.
    """

    model_config = ConfigDict(frozen=True)

    environment: Literal["development", "staging", "production"] = "development"
    """
    Deployment environment profile.
    Set AOS_ENVIRONMENT to 'staging' or 'production' for non-dev deployments.
    Currently informational; future packets use it to adjust defaults.
    """

    auth: AuthConfig = AuthConfig()
    database: DatabaseConfig = DatabaseConfig()
    vault: VaultConfig = VaultConfig()
    operator: OperatorConfig = OperatorConfig()
    openclaw: OpenClawConfig = OpenClawConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    dag: DAGConfig = DAGConfig()                          # D2 — DAG identity signing
    trust: TrustInfluenceConfig = TrustInfluenceConfig()  # L2 — trust influence mode
    lineage: LineageConfig = LineageConfig()               # L3 — lineage enforcement mode
    recovery: RecoveryExecutionConfig = RecoveryExecutionConfig()  # L5 — recovery execution mode
