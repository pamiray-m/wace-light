"""
WACE BYOK — bring-your-own LLM key (per-tenant Anthropic key).

A governor sets the tenant's own Anthropic API key in the Command Center. It is
sealed with the platform vault (AES-256-GCM under AOS_VAULT_KEY) before it ever
touches the DB — only a masked hint is ever returned to the UI. Agent runs then
route through the tenant's key (their Anthropic account is billed), still
SAIb-scrubbed and receipted.

`allow_platform_fallback` is the isolation knob:
  - key set + fallback ON   → tenant key; may fall back to the platform bridge if it fails.
  - key set + fallback OFF  → tenant key ONLY; a failure surfaces, never the platform.
  - no key + fallback ON    → the shared platform key (default, pre-BYOK behavior).
  - no key + fallback OFF   → the AI is disabled until the tenant configures a key.
"""

from __future__ import annotations

from typing import Optional

from src.aos.voundry.governance import voundry_audit
from src.aos.voundry.persistence.repository import voundry_repo

_KV = "llm_byok"
_AAD = b"voundry-llm-byok"


class ByokError(Exception):
    pass


def set_llm_key(actor_id: str, api_key: str, allow_platform_fallback: bool = True,
                repo=voundry_repo, audit=voundry_audit) -> dict:
    key = (api_key or "").strip()
    if not (key.startswith("sk-ant-") or key.startswith("sk-")):
        raise ByokError("That doesn't look like an Anthropic API key (expected 'sk-ant-…').")
    from src.core.integrations.encryption import encrypt
    try:
        sealed = encrypt(key, aad=_AAD)
    except Exception as exc:  # noqa: BLE001 — vault key missing/malformed
        raise ByokError("Server vault is not configured — cannot store the key securely.") from exc
    hint = f"{key[:7]}…{key[-4:]}" if len(key) > 14 else "sk-…"
    repo.save_kv(_KV, {"sealed": sealed, "hint": hint, "allow_platform_fallback": bool(allow_platform_fallback)})
    audit.append(actor_id=actor_id, actor_type="human", action="llm.byok_set",
                 resource_type="org", resource_id="org", detail=f"tenant LLM key set ({hint})",
                 metadata={"allow_platform_fallback": bool(allow_platform_fallback)})
    return llm_config(repo=repo)


def clear_llm_key(actor_id: str, repo=voundry_repo, audit=voundry_audit) -> dict:
    repo.save_kv(_KV, {})
    audit.append(actor_id=actor_id, actor_type="human", action="llm.byok_cleared",
                 resource_type="org", resource_id="org", detail="tenant LLM key removed")
    return llm_config(repo=repo)


def llm_config(repo=voundry_repo) -> dict:
    """Public (non-secret) BYOK status for the UI."""
    kv = repo.get_kv(_KV) or {}
    return {"configured": bool(kv.get("sealed")), "hint": kv.get("hint", ""),
            "allow_platform_fallback": bool(kv.get("allow_platform_fallback", True))}


def allow_platform_fallback(repo=voundry_repo) -> bool:
    return bool((repo.get_kv(_KV) or {}).get("allow_platform_fallback", True))


def tenant_api_key(repo=voundry_repo) -> Optional[str]:
    """Decrypt the tenant's BYOK key, or None if unset/unreadable."""
    sealed = (repo.get_kv(_KV) or {}).get("sealed")
    if not sealed:
        return None
    try:
        from src.core.integrations.encryption import decrypt
        return decrypt(sealed, aad=_AAD)
    except Exception:  # noqa: BLE001 — never leak a decrypt failure; behave as unset
        return None
