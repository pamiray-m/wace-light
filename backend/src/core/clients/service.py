from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
from jose import jwt, JWTError
from sqlalchemy.exc import IntegrityError

from src.core.registry.database import get_session
from src.core.clients.models import ClientAccount, ClientSubscription, AgentDirective

SECRET  = os.environ.get("AOS_JWT_SECRET", "dev-secret-change-me")
ALG     = "HS256"
EXPIRY  = int(os.environ.get("AOS_JWT_EXPIRY_MINUTES", "60"))


class ClientConflict(Exception):
    pass

class ClientNotFound(Exception):
    pass

class InvalidCredentials(Exception):
    pass


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def register_client(email: str, password: str, full_name: str, company: str | None) -> ClientAccount:
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    acct   = ClientAccount(email=email.lower().strip(), hashed_password=hashed,
                           full_name=full_name, company=company)
    db = get_session()
    try:
        db.add(acct)
        db.commit()
        db.refresh(acct)
    except IntegrityError:
        db.rollback()
        raise ClientConflict(f"Email already registered: {email}")
    finally:
        db.close()
    return acct


def authenticate_client(email: str, password: str) -> ClientAccount:
    db = get_session()
    try:
        acct = db.query(ClientAccount).filter_by(email=email.lower().strip()).first()
    finally:
        db.close()
    if not acct or not acct.is_active:
        raise InvalidCredentials()
    if not bcrypt.checkpw(password.encode(), acct.hashed_password.encode()):
        raise InvalidCredentials()
    db = get_session()
    try:
        db.query(ClientAccount).filter_by(id=acct.id).update(
            {"last_login_at": datetime.now(timezone.utc)}
        )
        db.commit()
    finally:
        db.close()
    return acct


def get_client_by_id(client_id: str) -> ClientAccount:
    db = get_session()
    try:
        acct = db.query(ClientAccount).filter_by(id=client_id).first()
    finally:
        db.close()
    if not acct:
        raise ClientNotFound(client_id)
    return acct


def issue_client_token(acct: ClientAccount) -> str:
    payload = {
        "sub":   acct.id,
        "email": acct.email,
        "name":  acct.full_name,
        "type":  "client",
        "iat":   datetime.now(timezone.utc),
        "exp":   datetime.now(timezone.utc) + timedelta(minutes=EXPIRY),
    }
    return jwt.encode(payload, SECRET, algorithm=ALG)


def verify_client_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALG])
        if payload.get("type") != "client":
            raise InvalidCredentials()
        return payload
    except JWTError:
        raise InvalidCredentials()


def google_auth_or_create(google_sub: str, email: str, full_name: str) -> ClientAccount:
    """Find or create a client account from a verified Google identity."""
    db = get_session()
    try:
        # Try by google_sub first, then fall back to email
        acct = db.query(ClientAccount).filter_by(google_sub=google_sub).first()
        if not acct:
            acct = db.query(ClientAccount).filter_by(email=email.lower().strip()).first()
        if acct:
            # Update google_sub if not already set
            if not acct.google_sub:
                acct.google_sub = google_sub
                db.commit()
                db.refresh(acct)
            return acct
        # Create new account
        acct = ClientAccount(
            email=email.lower().strip(),
            hashed_password="",  # no password for Google-only accounts
            full_name=full_name,
            google_sub=google_sub,
        )
        db.add(acct)
        db.commit()
        db.refresh(acct)
        return acct
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

def create_subscription(client_id: str, listing_id: str, agent_codename: str,
                         agent_name: str, agent_category: str, price_usd: float,
                         stripe_session_id: str | None = None) -> ClientSubscription:
    sub = ClientSubscription(
        client_id=client_id, listing_id=listing_id,
        agent_codename=agent_codename, agent_name=agent_name,
        agent_category=agent_category, price_usd=price_usd,
        stripe_session_id=stripe_session_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db = get_session()
    try:
        db.add(sub)
        db.commit()
        db.refresh(sub)
    finally:
        db.close()
    return sub


def get_subscriptions(client_id: str) -> list[ClientSubscription]:
    db = get_session()
    try:
        return db.query(ClientSubscription).filter_by(
            client_id=client_id, status="active"
        ).all()
    finally:
        db.close()


def get_subscriptions_all(client_id: str) -> list[ClientSubscription]:
    """All subscriptions for a client, including cancelled history. W2.7 self-service."""
    db = get_session()
    try:
        return db.query(ClientSubscription).filter_by(
            client_id=client_id,
        ).order_by(ClientSubscription.created_at.desc()).all()
    finally:
        db.close()


def get_subscription(client_id: str, subscription_id: str) -> ClientSubscription | None:
    db = get_session()
    try:
        return db.query(ClientSubscription).filter_by(
            id=subscription_id, client_id=client_id, status="active"
        ).first()
    finally:
        db.close()


def get_subscription_for_owner(
    client_id: str, subscription_id: str,
) -> ClientSubscription | None:
    """
    Self-service detail view: returns the subscription regardless of status, so
    customers can see cancelled history. Ownership is still enforced via client_id.
    """
    db = get_session()
    try:
        return db.query(ClientSubscription).filter_by(
            id=subscription_id, client_id=client_id,
        ).first()
    finally:
        db.close()


def cancel_client_subscription(
    client_id: str,
    subscription_id: str,
    reason: str | None = None,
) -> ClientSubscription | None:
    """
    Customer-initiated cancellation. Idempotent — calling on an already-cancelled
    subscription is a no-op that returns the existing row.

    If a Stripe subscription is attached, cancels it there too. Stripe failures
    are logged but do NOT block the local cancellation — operator audit picks up
    any drift later.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    db = get_session()
    try:
        sub = db.query(ClientSubscription).filter_by(
            id=subscription_id, client_id=client_id,
        ).first()
        if sub is None:
            return None
        if sub.status == "cancelled":
            return sub  # idempotent

        if sub.stripe_subscription_id:
            try:
                import stripe as _stripe
                _stripe.Subscription.cancel(sub.stripe_subscription_id)
            except Exception as exc:
                _log.warning(
                    "Stripe cancel for sub=%s stripe_id=%s failed: %s — proceeding with local cancel",
                    sub.id, sub.stripe_subscription_id, exc,
                )

        sub.status = "cancelled"
        sub.cancelled_at = datetime.now(timezone.utc)
        if reason:
            sub.cancellation_reason = reason[:255]
        db.commit()
        db.refresh(sub)
        return sub
    finally:
        db.close()


def get_subscription_by_session(stripe_session_id: str) -> ClientSubscription | None:
    db = get_session()
    try:
        return db.query(ClientSubscription).filter_by(
            stripe_session_id=stripe_session_id
        ).first()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Directives
# ---------------------------------------------------------------------------

def add_directive(client_id: str, subscription_id: str,
                  agent_codename: str, content: str) -> AgentDirective:
    d = AgentDirective(client_id=client_id, subscription_id=subscription_id,
                       agent_codename=agent_codename, content=content)
    db = get_session()
    try:
        db.add(d)
        db.commit()
        db.refresh(d)
    finally:
        db.close()
    return d


def get_directives(client_id: str, subscription_id: str) -> list[AgentDirective]:
    db = get_session()
    try:
        return db.query(AgentDirective).filter_by(
            client_id=client_id, subscription_id=subscription_id
        ).order_by(AgentDirective.created_at.desc()).limit(20).all()
    finally:
        db.close()


def update_directive_response(directive_id: str, response: str) -> None:
    db = get_session()
    try:
        db.query(AgentDirective).filter_by(id=directive_id).update({
            "response": response,
            "status": "completed",
            "responded_at": datetime.now(timezone.utc),
        })
        db.commit()
    finally:
        db.close()
