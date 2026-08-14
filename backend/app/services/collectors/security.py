"""URL / SSRF safety for anything the collection layer fetches over the
network (a source's own URL, its robots.txt, or a redirect target).

Two checks, deliberately kept separate:

- validate_url_shape: format-only (scheme, host present). No network call —
  safe to run at data-source create/update time.
- validate_url_ssrf: resolves DNS and rejects any address that is private,
  loopback, link-local, reserved, or a multicast/unspecified address. Must
  run immediately before every fetch (including each redirect hop), never
  cached, since DNS can change between calls (DNS-rebinding).
"""
import ipaddress
import socket
from contextlib import contextmanager
from urllib.parse import urlparse

import urllib3.util.connection as _urllib3_connection
from flask import current_app

from app.errors.exceptions import CollectionError

ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}


def validate_url_shape(url):
    if not url or not isinstance(url, str):
        raise CollectionError("The source URL is missing.", code="COLLECTION_INVALID_URL")
    try:
        parsed = urlparse(url)
    except ValueError:
        raise CollectionError("The source URL is not well-formed.", code="COLLECTION_INVALID_URL")

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise CollectionError(
            f"Unsupported URL scheme '{parsed.scheme or ''}'. Only http/https are permitted.",
            code="COLLECTION_INVALID_URL",
        )
    if not parsed.hostname:
        raise CollectionError("The source URL has no host.", code="COLLECTION_INVALID_URL")
    if parsed.hostname.lower() in _BLOCKED_HOSTNAMES and not _private_targets_allowed():
        raise CollectionError("Requests to localhost are not permitted.", code="COLLECTION_SSRF_BLOCKED")
    return parsed


def _private_targets_allowed():
    try:
        return bool(current_app.config.get("SCRAPER_ALLOW_PRIVATE_TARGETS"))
    except RuntimeError:
        return False  # no app context (e.g. a standalone script) -> always safe default


def _is_unsafe_ip(ip_str):
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # can't parse it -> treat as unsafe, never fail open
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def validate_url_ssrf(url):
    """Format check + DNS resolution + IP-range check. Raises CollectionError
    on anything unsafe. Returns the parsed URL on success. Call this again
    for every redirect hop — never trust a URL that hasn't just been checked.
    """
    parsed = validate_url_shape(url)
    hostname = parsed.hostname.lower()

    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise CollectionError("The source URL's host could not be resolved.", code="COLLECTION_INVALID_URL")
    except OSError:
        raise CollectionError("The source URL's host could not be resolved.", code="COLLECTION_INVALID_URL")

    if not addrinfo:
        raise CollectionError("The source URL's host could not be resolved.", code="COLLECTION_INVALID_URL")

    if not _private_targets_allowed():
        for family, _type, _proto, _canon, sockaddr in addrinfo:
            ip_str = sockaddr[0]
            if _is_unsafe_ip(ip_str):
                raise CollectionError(
                    "Requests to localhost or private/internal network addresses are not permitted.",
                    code="COLLECTION_SSRF_BLOCKED",
                )
    return parsed


_real_create_connection = _urllib3_connection.create_connection


def _ssrf_checked_create_connection(address, *args, **kwargs):
    """Drop-in replacement for urllib3's own connect entrypoint. This is
    what actually closes the DNS-rebinding gap: validate_url_ssrf() and the
    real TCP connect are two separate DNS lookups with a time gap between
    them: an attacker controlling DNS for their own domain could flip the
    A record between the two, so a hostname that resolved to a public IP at
    validation time could resolve to a private IP by connection time. This
    hook re-validates the literal address urllib3 is about to connect to,
    inside its own connect path — not a separate earlier check.
    """
    host = address[0]
    if not _private_targets_allowed():
        try:
            infos = socket.getaddrinfo(host, address[1])
        except OSError:
            infos = []
        for _family, _type, _proto, _canon, sockaddr in infos:
            if _is_unsafe_ip(sockaddr[0]):
                raise CollectionError(
                    "Requests to localhost or private/internal network addresses are not permitted.",
                    code="COLLECTION_SSRF_BLOCKED",
                )
    return _real_create_connection(address, *args, **kwargs)


@contextmanager
def ssrf_safe_connections():
    """Scopes urllib3's connect entrypoint to the SSRF-checked version for
    the duration of one collector HTTP call. Every session.get() in
    static_html.py/robots.py must run inside this context.

    Not thread-safe across concurrent collection requests in the same
    process (it patches a module-level function) — acceptable because
    collection is synchronous-within-one-request throughout this codebase
    (see docs/phase6_agent_handoff.md); revisit if collection is ever made
    concurrent within a single process.
    """
    _urllib3_connection.create_connection = _ssrf_checked_create_connection
    try:
        yield
    finally:
        _urllib3_connection.create_connection = _real_create_connection
