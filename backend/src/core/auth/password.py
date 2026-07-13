"""
H1 — Password hashing utilities.

Uses bcrypt directly.  All password operations go through this module;
no route or service may call bcrypt directly.

Security properties
-------------------
- bcrypt is used with 12 rounds (default cost factor).
- verify() is timing-safe (bcrypt.checkpw uses constant-time comparison).
- hash() raises ValueError on blank input so callers cannot accidentally hash
  empty strings during seeding.

Note: passlib is not used here because bcrypt>=4.0 removed the __about__
module that passlib relies on for version detection.  We call the bcrypt
library directly, which is stable across all recent versions.
"""

from __future__ import annotations

import bcrypt

_ROUNDS = 12


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*.  Raises ValueError if plain is empty."""
    if not plain:
        raise ValueError("Cannot hash an empty password.")
    salt = bcrypt.gensalt(rounds=_ROUNDS)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True iff *plain* matches *hashed*.  Never raises."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False
