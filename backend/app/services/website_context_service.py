"""Optional business-context website extraction.

Used only when a user opts in by entering a public website URL on a
project. The product works fully without a URL; the URL is an
enhancement, never a requirement.

What this service does
----------------------
  - Validates the URL using the existing collector SSRF layer
    (``app.services.collectors.security``). Reuses the same shape check,
    DNS-resolution IP-range check, and connection-time rebinding check.
  - Fetches a single page (no crawling beyond the URL itself) under the
    existing ``SCRAPER_REQUEST_TIMEOUT_SECONDS``, ``SCRAPER_MAX_RESPONSE_MB``,
    ``SCRAPER_USER_AGENT`` settings. The 1-page rule is a deliberate
    non-feature: a controlled, bounded read, not a crawler.
  - Extracts a small, useful set of business-context fields:
      * ``title``             (page <title>)
      * ``metaDescription``   (page <meta name="description">)
      * ``headings``          (top 8 <h1>/<h2> texts)
      * ``bodyExcerpt``       (truncated visible text)
      * ``sourceUrl``         (the original URL, normalized)
  - Hashes the content with SHA-256 so callers can detect drift without
    comparing full strings.
  - Records extraction status: ``"ok" | "blocked" | "fetch_failed" |
    "parse_failed" | "too_large"`` plus a safe ``failureReason`` string.

What this service does NOT do
-----------------------------
  - It does not crawl. A bounded single page read.
  - It does not send the entire page to the LLM. The LLM only sees
    the small structured extraction above.
  - It does not follow redirects to private IPs. Every redirect hop is
    re-validated by the same SSRF machinery.
  - It does not store raw HTML. Only the structured extraction is kept.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup
from flask import current_app

from app.errors.exceptions import CollectionError
from app.services.collectors.security import (
    ssrf_safe_connections,
    validate_url_shape,
    validate_url_ssrf,
)

logger = logging.getLogger(__name__)


# --- Status taxonomy (kept short + stable for the UI) -----------------------

STATUS_OK = "ok"
STATUS_BLOCKED = "blocked"
STATUS_FETCH_FAILED = "fetch_failed"
STATUS_PARSE_FAILED = "parse_failed"
STATUS_TOO_LARGE = "too_large"

ALL_STATUSES = (STATUS_OK, STATUS_BLOCKED, STATUS_FETCH_FAILED, STATUS_PARSE_FAILED, STATUS_TOO_LARGE)


@dataclass
class ExtractionResult:
    url: str
    status: str
    title: str = ""
    meta_description: str = ""
    headings: list = None
    body_excerpt: str = ""
    content_hash: str = ""
    failure_reason: str = ""
    elapsed_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sourceUrl": self.url,
            "status": self.status,
            "title": self.title,
            "metaDescription": self.meta_description,
            "headings": list(self.headings or []),
            "bodyExcerpt": self.body_excerpt,
            "contentHash": self.content_hash,
            "failureReason": self.failure_reason or None,
            "elapsedMs": self.elapsed_ms,
        }


# --- Internal helpers --------------------------------------------------------


def _normalize_url(url: str) -> str:
    return url.strip()


def _is_html_response(content_type: str) -> bool:
    if not content_type:
        return False
    return "html" in content_type.lower()


# A website page can attempt prompt-injection: content designed to break
# out of the LLM prompt's untrusted-content markers. The extraction layer
# strips those markers before any content is stored, so the prompt
# boundary cannot be crossed by page data.
_DELIMITER_PATTERN = re.compile(r"<<<\s*(BEGIN|END)\s+UNTRUSTED[^>]*>>>", re.IGNORECASE)


def _scrub(text: str) -> str:
    if not text:
        return ""
    text = _DELIMITER_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_fields(html: str, source_url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html or "", "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = _scrub(soup.title.string)[:400]

    meta_description = ""
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        meta_description = _scrub(md["content"])[:600]

    headings: list = []
    for tag in soup.find_all(["h1", "h2"]):
        text = _scrub(tag.get_text(" ", strip=True))
        if text and text not in headings:
            headings.append(text)
        if len(headings) >= 8:
            break

    for tag in soup(["script", "style", "noscript", "iframe", "svg", "template"]):
        tag.decompose()

    body_text = _scrub(soup.get_text(" "))
    body_excerpt = body_text[:1800]

    return {
        "title": title,
        "metaDescription": meta_description,
        "headings": headings,
        "bodyExcerpt": body_excerpt,
    }


def _hash_content(text: str) -> str:
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


# --- Public API --------------------------------------------------------------


def validate_url(url: str) -> str:
    """Format-only check. Returns the URL on success, raises on failure.
    Used by both the API layer and tests. The full SSRF check
    (DNS + IP-range) happens at extraction time, not here, so a user
    can save a URL and only fetch it on demand.
    """
    if not url or not isinstance(url, str):
        raise CollectionError("A website URL is required.", code="WEBSITE_INVALID_URL", status_code=400)
    cleaned = _normalize_url(url)
    try:
        validate_url_shape(cleaned)
    except CollectionError as exc:
        # Re-raise with our error code so the API layer returns 400.
        raise CollectionError(str(exc.message)[:300], code="WEBSITE_INVALID_URL", status_code=400)
    return cleaned


def extract_website_context(url: str, *, max_bytes: Optional[int] = None) -> ExtractionResult:
    """Fetch a single public page safely and return a small structured
    extraction. Never raises on network failure — returns a result with
    status set so the caller can decide what to render.

    Reads ``SCRAPER_REQUEST_TIMEOUT_SECONDS``, ``SCRAPER_MAX_RESPONSE_MB``,
    and ``SCRAPER_USER_AGENT`` from the current Flask app config.
    """
    started_ms = _now_ms()
    url = _normalize_url(url)

    # 1. Shape check (cheap, no DNS)
    try:
        validate_url_shape(url)
    except CollectionError as exc:
        return ExtractionResult(
            url=url, status=STATUS_BLOCKED,
            failure_reason=str(exc.message)[:200], elapsed_ms=_now_ms() - started_ms,
        )

    # 2. SSRF check (DNS resolution + IP-range check)
    try:
        validate_url_ssrf(url)
    except CollectionError as exc:
        return ExtractionResult(
            url=url, status=STATUS_BLOCKED,
            failure_reason=str(exc.message)[:200], elapsed_ms=_now_ms() - started_ms,
        )

    # 3. Bounded fetch
    timeout = int(current_app.config.get("SCRAPER_REQUEST_TIMEOUT_SECONDS", 15) or 15)
    response_max_mb = float(current_app.config.get("SCRAPER_MAX_RESPONSE_MB", 5) or 5)
    response_max_bytes = int(max_bytes if max_bytes is not None else response_max_mb * 1024 * 1024)
    user_agent = current_app.config.get("SCRAPER_USER_AGENT", "AgenticSentimentSystem/1.0")

    try:
        with ssrf_safe_connections():
            resp = requests.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
                headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"},
            )
    except requests.Timeout:
        return ExtractionResult(
            url=url, status=STATUS_FETCH_FAILED, failure_reason="Request timed out.",
            elapsed_ms=_now_ms() - started_ms,
        )
    except requests.RequestException as exc:
        return ExtractionResult(
            url=url, status=STATUS_FETCH_FAILED, failure_reason=str(exc)[:200],
            elapsed_ms=_now_ms() - started_ms,
        )

    # 4. Status / content-type / size guard
    if resp.status_code < 200 or resp.status_code >= 300:
        return ExtractionResult(
            url=url, status=STATUS_FETCH_FAILED,
            failure_reason=f"Upstream returned HTTP {resp.status_code}.",
            elapsed_ms=_now_ms() - started_ms,
        )

    if not _is_html_response(resp.headers.get("Content-Type", "")):
        return ExtractionResult(
            url=url, status=STATUS_PARSE_FAILED,
            failure_reason="Response was not HTML.",
            elapsed_ms=_now_ms() - started_ms,
        )

    chunks = []
    total = 0
    too_large = False
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > response_max_bytes:
            too_large = True
            break
        chunks.append(chunk)
    if too_large:
        return ExtractionResult(
            url=url, status=STATUS_TOO_LARGE,
            failure_reason=f"Response exceeded {response_max_bytes} bytes.",
            elapsed_ms=_now_ms() - started_ms,
        )

    try:
        html = b"".join(chunks).decode(resp.encoding or "utf-8", errors="ignore")
    except Exception as exc:
        return ExtractionResult(
            url=url, status=STATUS_PARSE_FAILED, failure_reason=str(exc)[:200],
            elapsed_ms=_now_ms() - started_ms,
        )

    try:
        fields = _extract_fields(html, url)
    except Exception as exc:
        return ExtractionResult(
            url=url, status=STATUS_PARSE_FAILED, failure_reason=str(exc)[:200],
            elapsed_ms=_now_ms() - started_ms,
        )

    return ExtractionResult(
        url=url,
        status=STATUS_OK,
        title=fields["title"],
        meta_description=fields["metaDescription"],
        headings=fields["headings"],
        body_excerpt=fields["bodyExcerpt"],
        content_hash=_hash_content(html),
        failure_reason="",
        elapsed_ms=_now_ms() - started_ms,
    )


def _now_ms() -> int:
    import time
    return int(time.monotonic() * 1000)
