"""
CredentialVault — product-scoped AES-GCM credential storage (H4).

Design
------
The vault is stateless: it holds no credentials itself.  Instead, it transforms
credential strings on the way in (seal) and out (unseal).  The encrypted blob is
stored in ToolBindingRecord.vaulted_credentials_ref, exactly where the plaintext
stub was before H4.

Product isolation — cryptographic, not just logical
----------------------------------------------------
The product_id is passed as AES-GCM Additional Authenticated Data (AAD).
AESGCM includes the AAD in the authentication tag that is appended to the
ciphertext.  If you attempt to unseal with a different product_id, the tag
verification fails before any plaintext is returned → CredentialDecryptionError.

This means cross-product access is blocked at the cryptographic layer even if
a caller somehow obtains the raw ciphertext bytes from the database.

No secret leakage
-----------------
- seal() and unseal() never log the plaintext.
- The CredentialVault instance holds no in-memory credential state.
- The AOS_VAULT_KEY is read from env at call time (see encryption.py).

Usage
-----
    vault = CredentialVault()

    # On tool assignment — store encrypted credential
    ref = vault.seal("product-A", "my-secret-api-key")
    # `ref` is a base64 ciphertext → stored in ToolBindingRecord

    # On ticket issuance — retrieve decrypted credential
    plaintext = vault.unseal("product-A", ref)      # succeeds
    vault.unseal("product-B", ref)                   # CredentialDecryptionError
"""

from __future__ import annotations

import logging

from src.core.integrations.encryption import decrypt, encrypt
from src.core.integrations.exceptions import CredentialDecryptionError  # re-exported for callers

_log = logging.getLogger(__name__)


class CredentialVault:
    """
    Stateless credential vault backed by AES-256-GCM with product-scoped AAD.

    Construction never fails — the vault key is loaded lazily when seal() or
    unseal() is first called.  This allows the service to start without
    AOS_VAULT_KEY as long as no credentials are actually processed.
    """

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def seal(self, product_id: str, plaintext_credential: str) -> str:
        """
        Encrypt *plaintext_credential* and bind the ciphertext to *product_id*.

        Parameters
        ----------
        product_id            : The owning product.  Used as AES-GCM AAD so the
                                ciphertext cannot be decrypted for any other product.
        plaintext_credential  : The raw credential string (API key, token, etc.).

        Returns
        -------
        Opaque base64 string suitable for storage in vaulted_credentials_ref.

        Raises
        ------
        VaultKeyMissing : AOS_VAULT_KEY is missing or malformed.
        """
        aad = product_id.encode("utf-8")
        try:
            result = encrypt(plaintext_credential, aad=aad)
            _log.debug(
                "vault.seal",
                extra={"event": "vault.seal", "product_id": product_id},
            )
            return result
        except Exception as exc:
            _log.warning(
                "vault.seal_failed",
                extra={"event": "vault.seal_failed",
                       "product_id": product_id,
                       "exc_type": type(exc).__name__},
            )
            raise

    def unseal(self, product_id: str, vaulted_ref: str) -> str:
        """
        Decrypt a credential previously sealed for *product_id*.

        Parameters
        ----------
        product_id   : Must exactly match the product_id used during seal().
                       Any mismatch causes AES-GCM tag verification to fail.
        vaulted_ref  : The base64 ciphertext from vaulted_credentials_ref.

        Returns
        -------
        The original plaintext credential string.

        Raises
        ------
        VaultKeyMissing           : AOS_VAULT_KEY is missing or malformed.
        CredentialDecryptionError : Wrong product_id, wrong key, or corrupted data.
        """
        aad = product_id.encode("utf-8")
        try:
            result = decrypt(vaulted_ref, aad=aad)
            _log.debug(
                "vault.unseal",
                extra={"event": "vault.unseal", "product_id": product_id},
            )
            return result
        except CredentialDecryptionError:
            _log.warning(
                "vault.unseal_failed",
                extra={"event": "vault.unseal_failed",
                       "product_id": product_id,
                       "exc_type": "CredentialDecryptionError"},
            )
            raise
        except Exception as exc:
            _log.warning(
                "vault.unseal_failed",
                extra={"event": "vault.unseal_failed",
                       "product_id": product_id,
                       "exc_type": type(exc).__name__},
            )
            raise
