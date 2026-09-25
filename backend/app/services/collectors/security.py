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
import threading
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

# The SSRF connect-time check is applied via a thread-local opt-in rather
# than swapping urllib3's module-level create_connection for the duration of
# a request. The old swap/restore pattern was a process-wide race: a second
# guarded fetch (e.g. a website-context refresh while a collection was
# running) would see the original function restored by the first request's
# finally-block mid-flight, silently losing the connect-time check for the
# remainder of its fetch. Here the checked function is installed exactly once
# at import time and delegates to the real implementation unless the calling
# thread has marked itself guarded, so concurrent guarded fetches never
# interfere and unrelated traffic (tests, non-collector requests) is
# untouched. _guard_state is per-thread; a nested guarded context is a no-op
# re-set of the same flag.
_guard_state = threading.local()


def _ssrf_checked_create_connection(address, *args, **kwargs):
    """Drop-in replacement for urllib3's own connect entrypoint. This is
    what actually closes the DNS-rebinding gap: validate_url_ssrf() and the
    real TCP connect are two separate DNS lookups with a time gap between
    them: an attacker controlling DNS for their own domain could flip the
    A record between the two, so a hostname that resolved to a public IP at
    validation time could resolve to a private IP by connection time. This
    hook re-validates the literal address urllib3 is about to connect to,
    inside its own connect path — not a separate earlier check.

    Unconditionally validating (public contract, pinned by tests); callers
    that should skip the check use _guarded_create_connection instead.
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


def _guarded_create_connection(address, *args, **kwargs):
    """The function actually installed as urllib3's create_connection.
    Runs the SSRF connect-time check only when the calling thread has armed
    it via ssrf_safe_connections(); otherwise a transparent pass-through, so
    non-collector traffic (tests, health checks, unrelated libraries) is
    never affected by this module being imported."""
    if getattr(_guard_state, "active", False):
        return _ssrf_checked_create_connection(address, *args, **kwargs)
    return _real_create_connection(address, *args, **kwargs)


def ssrf_guard_active() -> bool:
    """True when the current thread is inside an ssrf_safe_connections()
    context (connect-time re-validation is armed)."""
    return bool(getattr(_guard_state, "active", False))


@contextmanager
def ssrf_safe_connections():
    """Arms the connect-time SSRF re-validation for the duration of one
    collector HTTP call. Every session.get() in static_html.py/robots.py
    must run inside this context.

    This is thread-local by design: concurrent guarded fetches in the same
    process (collection + website-context refresh) each arm only their own
    thread, so no request can un-guard another. The flag is saved and
    restored, making nested guarded contexts safe.
    """
    previous = getattr(_guard_state, "active", False)
    _guard_state.active = True
    try:
        yield
    finally:
        _guard_state.active = previous


# Install the guarded wrapper once. Outside a guarded context it behaves
# exactly like urllib3's original.
_urllib3_connection.create_connection = _guarded_create_connection
