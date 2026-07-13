"""
W3.5 — SOC2-ready unified audit export.

Pulls records from the existing AA-5 and SAL-5 audit repositories, serializes
to NDJSON, and signs the body with HMAC-SHA256 so SOC2 auditors can verify
no record was tampered with after export.
"""
