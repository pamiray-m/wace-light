"""
SSRF-guarded HTTP fetcher.

Fetching attacker-controlled URLs is a classic SSRF vector (reach internal
services, cloud metadata at 169.254.169.254, etc.). Every URL — and every
redirect hop — is validated: scheme must be http/https, and the host must not
resolve to a private / loopback / link-local / reserved / multicast address.
Responses are size-capped (streamed) and redirect-bounded.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

DEFAULT_UA = "AOS-1-SmartScraper/1.0 (+https://aos-1.com)"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 3_000_000      # 3 MB cap on downloaded body
DEFAULT_MAX_REDIRECTS = 5


class SSRFError(Exception):
    """URL rejected by the SSRF guard."""


class FetchError(Exception):
    """Network / HTTP / size / redirect failure."""


def _host_resolves_safe(host: str) -> bool:
    """True only if every resolved address for `host` is a public address."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        # Strip IPv6 zone id if present (e.g. "fe80::1%lo0").
        addr = addr.split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def validate_url(url: str) -> str:
    """Validate a single URL against the SSRF policy. Returns the host."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"unsupported scheme {parsed.scheme!r} (http/https only)")
    host = parsed.hostname
    if not host:
        raise SSRFError("URL has no host")
    if not _host_resolves_safe(host):
        raise SSRFError(f"host {host!r} resolves to a non-public/internal address")
    return host


def _pin_target(url: str, resolve=None) -> tuple[str, str]:
    """Validate a URL and pin it to a single validated public IP.

    Defeats DNS-rebinding / TOCTOU: `validate_url` resolves + checks, but a
    plain httpx call re-resolves independently, so a host that answers with a
    public IP during validation and an internal IP at connect time would slip
    through. Here we resolve ONCE, reject if any address is non-public, and
    return a URL whose host is the chosen IP literal (so the connection cannot
    be re-resolved) plus the original hostname (for the Host header + TLS SNI).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"unsupported scheme {parsed.scheme!r} (http/https only)")
    host = parsed.hostname
    if not host:
        raise SSRFError("URL has no host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolve = resolve or socket.getaddrinfo   # bind at call time so tests can patch
    try:
        infos = resolve(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFError(f"host {host!r} does not resolve") from exc
    chosen: str | None = None
    for info in infos:
        addr = info[4][0].split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise SSRFError(f"host {host!r} resolved to an invalid address")
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise SSRFError(f"host {host!r} resolves to a non-public/internal address")
        if chosen is None:
            chosen = addr
    if chosen is None:
        raise SSRFError(f"host {host!r} did not resolve to any address")
    hostpart = f"[{chosen}]" if ipaddress.ip_address(chosen).version == 6 else chosen
    netloc = f"{hostpart}:{parsed.port}" if parsed.port else hostpart
    pinned = parsed._replace(netloc=netloc).geturl()
    return pinned, host


def safe_request(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    json=None,
    content=None,
    timeout: float = DEFAULT_TIMEOUT,
) -> httpx.Response:
    """SSRF-safe one-shot request pinned to a validated IP (no redirects).

    The connection targets the exact IP validated by `_pin_target`; the Host
    header and TLS SNI carry the real hostname, so HTTPS cert verification is
    unaffected. Use this for any request to a caller-influenced URL.
    """
    pinned, host = _pin_target(url)
    hdrs = dict(headers or {})
    hdrs.setdefault("Host", host)
    with httpx.Client(follow_redirects=False, timeout=timeout,
                      headers={"User-Agent": DEFAULT_UA}) as client:
        req = client.build_request(method, pinned, headers=hdrs, json=json, content=content,
                                   extensions={"sni_hostname": host})
        return client.send(req)


def fetch(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    client: httpx.Client | None = None,
) -> tuple[str, str]:
    """Fetch `url` safely. Returns (final_url, html_text).

    Redirects are followed manually so each hop is re-validated by the SSRF
    guard (httpx's auto-redirect would not re-check the target). `client` is
    injectable for tests.
    """
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            follow_redirects=False, timeout=timeout,
            headers={"User-Agent": DEFAULT_UA, "Accept": "text/html,*/*"},
        )
    current = url
    try:
        for _ in range(max_redirects + 1):
            validate_url(current)               # raises SSRFError
            try:
                with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        loc = resp.headers.get("location")
                        if not loc:
                            raise FetchError("redirect without Location header")
                        current = urljoin(current, loc)
                        continue
                    if resp.status_code >= 400:
                        raise FetchError(f"HTTP {resp.status_code}")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in resp.iter_bytes():
                        chunks.append(chunk)
                        total += len(chunk)
                        if total >= max_bytes:
                            break
                    body = b"".join(chunks)[:max_bytes]
                    encoding = resp.encoding or "utf-8"
                    return current, body.decode(encoding, errors="replace")
            except httpx.HTTPError as exc:
                raise FetchError(f"request failed: {exc}") from exc
        raise FetchError(f"too many redirects (>{max_redirects})")
    finally:
        if owns_client:
            client.close()
