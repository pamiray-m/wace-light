"""
P2 — Configuration loader.

Single entry point for all AOS configuration.  Business modules import and
call ``get_settings()`` instead of reading ``os.environ`` directly.

Public API
----------
get_settings() -> Settings
    Read all configuration from the environment.  Returns a fully-populated
    ``Settings`` object.  Never raises — missing or empty values are returned
    as empty strings / defaults so that downstream validators (e.g. jwt.py)
    can raise their own domain-specific errors.

validate_settings(settings) -> None
    Check that all *production-required* fields are present and valid.
    Raises ``ConfigurationError`` with a human-readable list of every
    problem found.  Called once at application startup (see create_app()).

ConfigurationError
    RuntimeError subclass raised by ``validate_settings()``.

Design
------
get_settings() is deliberately *not* cached globally.  A fresh Settings
object is constructed on each call so that pytest's ``monkeypatch.setenv``
changes are visible without explicit cache-busting.  The cost is negligible
(a handful of os.environ lookups + Pydantic model construction).

validate_settings() is only called in production boot paths
(create_app() without an explicit db_url, i.e. non-test invocations).
Test code always passes db_url="sqlite:///:memory:" and therefore skips
the startup validation.
"""

from __future__ import annotations

import os

from src.config.models import (
    AuthConfig,
    DAGConfig,
    DatabaseConfig,
    LineageConfig,
    OpenClawConfig,
    OperatorConfig,
    RateLimitConfig,
    RecoveryExecutionConfig,
    Settings,
    TrustInfluenceConfig,
    VaultConfig,
)


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class ConfigurationError(RuntimeError):
    """
    Raised at application startup when required configuration is absent or
    malformed.

    The message contains every discovered problem so that operators can fix
    all issues in a single deployment attempt.
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


_VALID_LINEAGE_MODES    = frozenset({"off", "warn", "strict_high_risk", "strict_all_material"})
_VALID_TRUST_MODES      = frozenset({"off", "advisory", "warn", "strict_deprecated", "strict_low_trust"})
_VALID_RECOVERY_MODES   = frozenset({"off", "advisory", "safe_execute", "controlled", "full"})


# ---------------------------------------------------------------------------
# W3.1 — Governance profile master switch
# ---------------------------------------------------------------------------
#
# AOS_GOVERNANCE_PROFILE flips all four governance modes (trust, lineage,
# recovery, SAIb) together. Individual per-mode env vars still win when set.
# This is the feature-flagged "2-week soak" mechanism approved by Rami on
# 2026-05-12: ship default-STRICT to staging via this profile, with the
# option to flip back to permissive instantly if anything regresses.
#
# Profiles
# --------
# "permissive" (default)  trust=advisory  lineage=warn      recovery=advisory   saib=MASK
# "strict"                trust=strict_low_trust  lineage=strict_all_material  recovery=safe_execute  saib=STRICT
#
# Unknown / unset profile values fall back to "permissive" so existing tests
# and dev environments see no change.

_VALID_PROFILES = frozenset({"permissive", "strict"})

_PROFILE_DEFAULTS: dict[str, dict[str, str]] = {
    "permissive": {
        "trust":    "advisory",
        "lineage":  "warn",
        "recovery": "advisory",
        "saib":     "MASK",
    },
    "strict": {
        "trust":    "strict_low_trust",
        "lineage":  "strict_all_material",
        "recovery": "safe_execute",
        "saib":     "STRICT",
    },
}


def _governance_profile() -> str:
    """Return the active governance profile (validated, lowercased)."""
    raw = (os.environ.get("AOS_GOVERNANCE_PROFILE", "") or "").strip().lower()
    return raw if raw in _VALID_PROFILES else "permissive"


def _profile_default(key: str) -> str:
    """
    Return the per-mode default dictated by the active profile.

    `key` is one of: "trust", "lineage", "recovery", "saib".
    """
    return _PROFILE_DEFAULTS[_governance_profile()][key]


def _truthy(value: str) -> bool:
    """Return True for "true", "1", or "yes" (case-insensitive)."""
    return value.strip().lower() in ("true", "1", "yes")


def _lineage_mode(value: str) -> str:
    """Return value if it is a valid lineage enforcement mode, else the profile default."""
    sanitised = (value or "").strip().lower()
    if sanitised in _VALID_LINEAGE_MODES:
        return sanitised
    return _profile_default("lineage")


def _trust_mode(value: str) -> str:
    """Return value if it is a valid trust influence mode, else the profile default."""
    sanitised = (value or "").strip().lower()
    if sanitised in _VALID_TRUST_MODES:
        return sanitised
    return _profile_default("trust")


def _recovery_execution_mode(value: str) -> str:
    """Return value if it is a valid recovery execution mode, else the profile default."""
    sanitised = (value or "").strip().lower()
    if sanitised in _VALID_RECOVERY_MODES:
        return sanitised
    return _profile_default("recovery")


def saib_mode_default() -> str:
    """
    Public — used by src/saib/guard.py to honor AOS_GOVERNANCE_PROFILE when
    the per-mode AOS_SAIB_MODE env var is unset. Returns "MASK" / "STRICT" /
    "OFF" / "DETECT" (uppercase, matching SAIbMode enum values).
    """
    return _profile_default("saib")


def _float(value: str, default: float) -> float:
    """Parse *value* as float; return *default* on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _int(value: str, default: int) -> int:
    """Parse *value* as int; return *default* on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def get_settings() -> Settings:
    """
    Build a ``Settings`` object from the current environment.

    Reads every known AOS environment variable and returns a frozen
    ``Settings`` instance.  Does *not* raise — missing values are represented
    as empty strings or defaults.  Call ``validate_settings()`` separately
    when fail-fast behaviour is required (production startup).

    Call site pattern
    -----------------
    ::

        from src.config import get_settings

        def _do_something():
            cfg = get_settings()
            secret = cfg.auth.jwt_secret  # never os.environ directly
    """
    env = os.environ  # convenience alias

    return Settings(
        environment=env.get("AOS_ENVIRONMENT", "development"),  # type: ignore[arg-type]

        auth=AuthConfig(
            jwt_secret=env.get("AOS_JWT_SECRET", "").strip(),
            jwt_expiry_minutes=_int(env.get("AOS_JWT_EXPIRY_MINUTES", "15"), 15),
            refresh_expiry_days=_int(env.get("AOS_REFRESH_EXPIRY_DAYS", "7"), 7),
        ),

        vault=VaultConfig(
            vault_key=env.get("AOS_VAULT_KEY", ""),
        ),

        database=DatabaseConfig(
            url=env.get("AOS_DB_URL", "sqlite:///./aos_registry.db"),
        ),

        operator=OperatorConfig(
            username=env.get("AOS_OPERATOR_USERNAME", "admin").strip() or "admin",
            password=env.get("AOS_OPERATOR_PASSWORD", "").strip(),
            role=env.get("AOS_OPERATOR_ROLE", "admin").strip() or "admin",
            product_scope=env.get("AOS_OPERATOR_PRODUCT_SCOPE") or None,
            stream_scope=env.get("AOS_OPERATOR_STREAM_SCOPE") or None,
        ),

        openclaw=OpenClawConfig(
            enabled=_truthy(env.get("OPENCLAW_ENABLED", "false")),
            make_default=_truthy(env.get("OPENCLAW_DEFAULT", "false")),
            base_url=env.get("OPENCLAW_BASE_URL", "stub://openclaw-local"),
            api_key=env.get("OPENCLAW_API_KEY", ""),
            queue_name=env.get("OPENCLAW_QUEUE_NAME", "maib-tasks"),
            timeout_secs=_int(env.get("OPENCLAW_TIMEOUT_SECS", "10"), 10),
        ),

        rate_limit=RateLimitConfig(
            enabled=_truthy(env.get("AOS_RATE_LIMIT_ENABLED", "true")),
            auth_login_requests=_int(env.get("AOS_RATE_LIMIT_LOGIN_REQUESTS", "5"), 5),
            auth_login_window_seconds=_int(env.get("AOS_RATE_LIMIT_LOGIN_WINDOW", "60"), 60),
            auth_refresh_requests=_int(env.get("AOS_RATE_LIMIT_REFRESH_REQUESTS", "10"), 10),
            auth_refresh_window_seconds=_int(env.get("AOS_RATE_LIMIT_REFRESH_WINDOW", "60"), 60),
            auth_logout_requests=_int(env.get("AOS_RATE_LIMIT_LOGOUT_REQUESTS", "20"), 20),
            auth_logout_window_seconds=_int(env.get("AOS_RATE_LIMIT_LOGOUT_WINDOW", "60"), 60),
            control_requests=_int(env.get("AOS_RATE_LIMIT_CONTROL_REQUESTS", "30"), 30),
            control_window_seconds=_int(env.get("AOS_RATE_LIMIT_CONTROL_WINDOW", "60"), 60),
            mutation_requests=_int(env.get("AOS_RATE_LIMIT_MUTATION_REQUESTS", "20"), 20),
            mutation_window_seconds=_int(env.get("AOS_RATE_LIMIT_MUTATION_WINDOW", "60"), 60),
            default_requests=_int(env.get("AOS_RATE_LIMIT_DEFAULT_REQUESTS", "60"), 60),
            default_window_seconds=_int(env.get("AOS_RATE_LIMIT_DEFAULT_WINDOW", "60"), 60),
        ),

        # D2 — DAG identity signing key
        dag=DAGConfig(
            signing_key=env.get("AOS_DAG_SIGNING_KEY", "").strip(),
        ),

        # L2 Activation — trust influence mode and thresholds.
        # Pass empty-string default so _trust_mode falls back to the
        # AOS_GOVERNANCE_PROFILE default when the per-mode var is unset.
        trust=TrustInfluenceConfig(
            influence_mode=_trust_mode(  # type: ignore[arg-type]
                env.get("AOS_TRUST_INFLUENCE_MODE", "")
            ),
            low_trust_threshold=_float(
                env.get("AOS_TRUST_LOW_THRESHOLD", "0.4"), 0.4,
            ),
            critical_trust_threshold=_float(
                env.get("AOS_TRUST_CRITICAL_THRESHOLD", "0.1"), 0.1,
            ),
        ),

        # L3 Activation — lineage enforcement mode (profile-aware default).
        lineage=LineageConfig(
            enforcement_mode=_lineage_mode(  # type: ignore[arg-type]
                env.get("AOS_LINEAGE_ENFORCEMENT_MODE", "")
            ),
        ),

        # L5 Activation — recovery execution mode (profile-aware default).
        recovery=RecoveryExecutionConfig(
            execution_mode=_recovery_execution_mode(  # type: ignore[arg-type]
                env.get("AOS_RECOVERY_EXECUTION_MODE", "")
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Startup validator
# ---------------------------------------------------------------------------

_JWT_MIN_LEN = 32


def validate_settings(settings: Settings) -> None:
    """
    Assert that all production-required fields are present and valid.

    Collects *all* errors before raising so that operators see a complete
    list rather than fixing one issue at a time.

    Required for production boot
    ----------------------------
    - ``AOS_JWT_SECRET``        must be set and ≥ 32 characters.
    - ``AOS_OPERATOR_PASSWORD`` must be set (otherwise no one can log in).
    - ``AOS_VAULT_KEY``         must be valid base64 and decode to 32 bytes
                                if set (an empty value is allowed — vault
                                operations will fail at use time, not startup).

    Raises
    ------
    ConfigurationError
        If any required field is absent or malformed.  The message lists
        every problem found.
    """
    import base64

    errors: list[str] = []

    # --- Auth ----------------------------------------------------------------
    if not settings.auth.jwt_secret:
        errors.append(
            "AOS_JWT_SECRET is not set. "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
    elif len(settings.auth.jwt_secret) < _JWT_MIN_LEN:
        errors.append(
            f"AOS_JWT_SECRET must be at least {_JWT_MIN_LEN} characters "
            f"(currently {len(settings.auth.jwt_secret)})."
        )

    # --- Operator seed -------------------------------------------------------
    if not settings.operator.password:
        errors.append(
            "AOS_OPERATOR_PASSWORD is not set. "
            "No operators will be seeded — login will be impossible."
        )

    # --- Vault key (format only — presence is optional) ----------------------
    if settings.vault.vault_key:
        try:
            decoded = base64.b64decode(settings.vault.vault_key)
            if len(decoded) != 32:
                errors.append(
                    f"AOS_VAULT_KEY must decode to exactly 32 bytes; "
                    f"got {len(decoded)}. "
                    "Generate one with: python3 -c "
                    "\"import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
                )
        except Exception:
            errors.append(
                "AOS_VAULT_KEY is not valid base64. "
                "Generate one with: python3 -c "
                "\"import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
            )

    if errors:
        bullet_list = "\n".join(f"  • {e}" for e in errors)
        raise ConfigurationError(
            f"AOS startup configuration check failed "
            f"({len(errors)} error(s)):\n{bullet_list}"
        )
