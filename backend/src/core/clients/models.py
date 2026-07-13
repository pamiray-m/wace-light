from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from src.core.registry.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ClientAccount(Base):
    __tablename__ = "client_accounts"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email           = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False, default="")
    full_name       = Column(String(255), nullable=False)
    company         = Column(String(255), nullable=True)
    google_sub      = Column(String(255), nullable=True, unique=True, index=True)
    is_active       = Column(Boolean, nullable=False, default=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    last_login_at   = Column(DateTime(timezone=True), nullable=True)


class ClientSubscription(Base):
    __tablename__ = "client_subscriptions"

    id                     = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id              = Column(String(36), nullable=False, index=True)
    listing_id             = Column(String(36), nullable=False)
    agent_codename         = Column(String(128), nullable=False)
    agent_name             = Column(String(255), nullable=False)
    agent_category         = Column(String(64), nullable=False)
    price_usd              = Column(Float, nullable=False)
    stripe_session_id      = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    status                 = Column(String(32), nullable=False, default="active", index=True)
    created_at             = Column(DateTime(timezone=True), nullable=False, default=_now)
    expires_at             = Column(DateTime(timezone=True), nullable=True)
    # W2.7 — customer self-service: cancellation audit trail
    cancelled_at           = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason    = Column(String(255), nullable=True)
    # W2.3 — receipt idempotency
    receipt_sent_at        = Column(DateTime(timezone=True), nullable=True)
    # W2.5 — Stripe Tax amount captured from webhook event (cents)
    tax_amount_cents       = Column(Integer, nullable=False, default=0)


class AgentDirective(Base):
    __tablename__ = "agent_directives"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id      = Column(String(36), nullable=False, index=True)
    subscription_id = Column(String(36), nullable=False, index=True)
    agent_codename = Column(String(128), nullable=False)
    content        = Column(String(4000), nullable=False)
    response       = Column(String(8000), nullable=True)
    status         = Column(String(32), nullable=False, default="pending")
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    responded_at   = Column(DateTime(timezone=True), nullable=True)
