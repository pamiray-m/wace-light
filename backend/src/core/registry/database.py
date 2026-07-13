"""
Database engine and session factory for the Agent Registry.

Stub: Uses SQLite by default (file-based or in-memory).
Production will swap the URL for PostgreSQL without touching service logic.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

# W5.4 — Importing this module attaches global SQLAlchemy Engine event
# listeners. Every Engine built via build_engine() (or anywhere else in the
# process) inherits per-query timing + slow-query telemetry. The import is
# the registration.
from src.core.observability import db_telemetry as _db_telemetry  # noqa: F401

_DEFAULT_URL = "sqlite:///./aos_registry.db"


class Base(DeclarativeBase):
    pass


def build_engine(url: str = _DEFAULT_URL):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    # In-memory SQLite requires StaticPool so that all sessions share the same
    # underlying connection (and therefore the same set of tables).  Without this,
    # each new session gets a fresh, empty database — making cross-session queries
    # fail with "no such table".
    if url == "sqlite:///:memory:":
        from sqlalchemy.pool import StaticPool
        return create_engine(
            url,
            connect_args=connect_args,
            poolclass=StaticPool,
        )
    if url.startswith("sqlite"):
        return create_engine(url, connect_args=connect_args)
    # PostgreSQL / other production engines — tune pool for concurrent load.
    return create_engine(
        url,
        connect_args=connect_args,
        pool_size=20,
        max_overflow=10,
        pool_recycle=3600,
        pool_pre_ping=True,
    )


# Module-level defaults — replaced in tests via init_db(url=":memory:")
_engine = build_engine()
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def init_db(url: str = _DEFAULT_URL) -> None:
    """Create all tables. Call once at application startup (or in test fixtures)."""
    global _engine, _SessionLocal
    _engine = build_engine(url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    from . import models  # noqa: F401 — ensures models are registered with Base
    Base.metadata.create_all(bind=_engine)


def get_session() -> Session:
    """Return a new SQLAlchemy session. Caller is responsible for close/commit."""
    return _SessionLocal()
