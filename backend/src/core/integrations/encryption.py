"""
AES-256-GCM symmetric encryption layer for the AOS Credential Vault (H4).

Key source
----------
AOS_VAULT_KEY environment variable (accessed via src.config, not os.environ
directly).  A base64-encoded 32-byte (256-bit) key.
The key is loaded lazily — only when encrypt() or decrypt() is actually called.
This means the service starts without the env var as long as no credentials are
stored or retrieved; callers that do pass credentials will receive VaultKeyMissing
if the key is absent.

Wire format
-----------
encrypt() returns a single base64 string:
    base64( <12-byte nonce> || <ciphertext + 16-byte GCM tag> )

The nonce is randomly generated per call (os.urandom).  The GCM tag is
appended by the AESGCM primitive automatically.

AAD (Additional Authenticated Data)
------------------------------------
Both encrypt() and decrypt() accept an optional *aad* parameter.  The vault
layer passes product_id.encode() as AAD so that each ciphertext is
cryptographically bound to its product.  Attempting to decrypt with a
different product_id fails at tag-verification time → CredentialDecryptionError.
This gives product isolation a cryptographic guarantee, not merely a DB check.

P2 note
-------
This module no longer reads os.environ directly.  The vault key is accessed
through get_settings() from src.config.  Key rotation without restart is
preserved because _load_key() calls get_settings() on every invocation.
"""

from __future__ import annotations

import base64
import os
from typing import Final, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.core.integrations.exceptions import CredentialDecryptionError, VaultKeyMissing

_NONCE_LEN: Final[int] = 12   # 96-bit nonce — NIST recommended for AES-GCM


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_key() -> bytes:
    """
    Read and validate AOS_VAULT_KEY from the central configuration.

    Raises VaultKeyMissing if the variable is absent, not valid base64, or does
    not decode to exactly 32 bytes.  Called on every encrypt/decrypt invocation
    so that monkeypatch-based tests and key rotation work without cache
    invalidation.
    """
    from src.config import get_settings
    raw = get_settings().vault.vault_key
    if not raw:
        raise VaultKeyMissing(
            "AOS_VAULT_KEY is not set. "
            "Provide a base64-encoded 32-byte key to use the credential vault."
        )
    try:
        key = base64.b64decode(raw)
    except Exception as exc:
        raise VaultKeyMissing(
            f"AOS_VAULT_KEY is not valid base64: {exc}"
        ) from exc
    if len(key) != 32:
        raise VaultKeyMissing(
            f"AOS_VAULT_KEY must decode to exactly 32 bytes; got {len(key)}."
        )
    return key


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def encrypt(plaintext: str, *, aad: Optional[bytes] = None) -> str:
    """
    Encrypt *plaintext* with AES-256-GCM.

    Parameters
    ----------
    plaintext : The credential string to encrypt.
    aad       : Additional Authenticated Data (e.g. product_id.encode()).
                Must be supplied identically to decrypt() or decryption fails.

    Returns
    -------
    Base64-encoded string: <12-byte nonce> || <ciphertext+tag>.
    The plaintext is never written to disk or logs by this function.

    Raises
    ------
    VaultKeyMissing : AOS_VAULT_KEY is missing or malformed.
    """
    key = _load_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(ciphertext_b64: str, *, aad: Optional[bytes] = None) -> str:
    """
    Decrypt a value produced by encrypt().

    Parameters
    ----------
    ciphertext_b64 : The base64 string returned by encrypt().
    aad            : Must match the AAD used during encryption exactly.
                     A mismatch causes tag-verification failure.

    Returns
    -------
    The original plaintext string.

    Raises
    ------
    VaultKeyMissing          : AOS_VAULT_KEY is missing or malformed.
    CredentialDecryptionError: Wrong key, wrong AAD, or corrupted ciphertext.
    """
    key = _load_key()
    try:
        raw = base64.b64decode(ciphertext_b64)
        if len(raw) < _NONCE_LEN:
            raise ValueError("Ciphertext is too short to contain a nonce.")
        nonce = raw[:_NONCE_LEN]
        body = raw[_NONCE_LEN:]
        aesgcm = AESGCM(key)
        plaintext_bytes = aesgcm.decrypt(nonce, body, aad)
        return plaintext_bytes.decode("utf-8")
    except (VaultKeyMissing, CredentialDecryptionError):
        raise
    except Exception as exc:
        raise CredentialDecryptionError(
            f"Credential decryption failed: {exc}"
        ) from exc
