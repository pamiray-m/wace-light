"""
WACE signed audit-export bundle.

Produces a tamper-evident, offline-verifiable evidence pack a customer can hand
to their auditor: the current governance policy, the org-wide WORM receipt
stream, and the coverage/value summary — all hashed (SHA-256 per file) and signed
with an Ed25519 key. The manifest carries the public key, so verification needs
nothing but the ZIP and any Ed25519 verifier.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.aos.voundry.persistence.repository import voundry_repo

_KV_ID = "wace_audit_key"


def _load_key(repo=voundry_repo):
    """Load the WACE audit signing key — env override, else a persisted key,
    else generate + persist one (stable across restarts)."""
    pem = (os.getenv("WACE_AUDIT_SIGNING_KEY", "") or "").strip()
    if pem:
        sk = serialization.load_pem_private_key(pem.encode(), password=None)
        pub = sk.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        return sk, pub, "wace-env"
    saved = repo.get_kv(_KV_ID)
    if saved and saved.get("private_pem"):
        sk = serialization.load_pem_private_key(saved["private_pem"].encode(), password=None)
        return sk, saved["public_pem"].encode(), saved.get("kid", "wace")
    sk = Ed25519PrivateKey.generate()
    priv = sk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    pub = sk.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    kid = "wace-" + hashlib.sha256(pub).hexdigest()[:12]
    repo.save_kv(_KV_ID, {"private_pem": priv.decode(), "public_pem": pub.decode(), "kid": kid})
    return sk, pub, kid


def _canonical(digests: dict) -> bytes:
    return "\n".join(f"{n}:{digests[n]}" for n in sorted(digests)).encode()


def _readme(org: str, now: str, kid: str) -> str:
    return (
        "WACE SIGNED AUDIT EXPORT\n"
        "========================\n\n"
        f"Organization : {org}\n"
        f"Generated    : {now}\n"
        f"Signing key  : {kid} (Ed25519)\n\n"
        "Contents\n"
        "--------\n"
        "  manifest.json  - per-file SHA-256 digests + the Ed25519 signature and public key.\n"
        "  policy.json    - the governance policy in force at export time.\n"
        "  summary.json   - coverage + value metrics (desks, connections, actions, hours saved).\n"
        "  receipts.jsonl - the append-only (WORM) receipt stream, one JSON object per line.\n\n"
        "How to verify (offline, no network, no WACE)\n"
        "--------------------------------------------\n"
        "  1. For each file listed in manifest.json['files'], recompute its SHA-256 and\n"
        "     confirm it matches.\n"
        "  2. Rebuild the canonical string: for every file name (sorted), the line\n"
        "     '<name>:<sha256>' joined by newlines.\n"
        "  3. Verify manifest.json['signature'].value_b64 (base64) against that canonical\n"
        "     string using the Ed25519 public key in signature.public_key_pem (base64 PEM).\n\n"
        "If both checks pass, the bundle is authentic and unmodified since export.\n"
    )


def build_bundle(*, summary: dict, receipts: list, policy: dict,
                 org: str = "AOS-1 / mAIb Tech", repo=voundry_repo,
                 now: Optional[str] = None) -> tuple[bytes, str]:
    """Build the signed ZIP. Returns (zip_bytes, filename)."""
    sk, pub_pem, kid = _load_key(repo)
    now = now or datetime.now(timezone.utc).isoformat()
    files: dict[str, bytes] = {
        "summary.json": json.dumps(summary, indent=2, sort_keys=True).encode(),
        "policy.json": json.dumps(policy, indent=2, sort_keys=True).encode(),
        "receipts.jsonl": ("\n".join(json.dumps(r, sort_keys=True, default=str) for r in receipts)).encode(),
        "README.txt": _readme(org, now, kid).encode(),
    }
    digests = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    canonical = _canonical(digests)
    manifest = {
        "bundle": "WACE Signed Audit Export", "org": org, "generated_at": now,
        "files": digests, "bundle_digest_sha256": hashlib.sha256(canonical).hexdigest(),
        "counts": {"receipts": len(receipts)},
        "signature": {"algorithm": "Ed25519", "kid": kid,
                      "value_b64": base64.b64encode(sk.sign(canonical)).decode(),
                      "public_key_pem": base64.b64encode(pub_pem).decode()},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True).encode())
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue(), f"wace-audit-export-{now[:10]}.zip"


def verify_bundle(zip_bytes: bytes) -> dict:
    """Offline verification: recompute per-file digests + check the Ed25519 signature."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        manifest = json.loads(z.read("manifest.json"))
        digests = {name: hashlib.sha256(z.read(name)).hexdigest() for name in manifest["files"]}
    files_ok = digests == manifest["files"]
    sig = manifest["signature"]
    pub = serialization.load_pem_public_key(base64.b64decode(sig["public_key_pem"]))
    try:
        pub.verify(base64.b64decode(sig["value_b64"]), _canonical(digests))
        sig_ok = True
    except Exception:  # noqa: BLE001
        sig_ok = False
    return {
        "verified": bool(files_ok and sig_ok), "files_ok": files_ok, "signature_ok": sig_ok,
        "kid": sig["kid"], "org": manifest.get("org"), "generated_at": manifest.get("generated_at"),
        "counts": manifest.get("counts", {}),
    }
