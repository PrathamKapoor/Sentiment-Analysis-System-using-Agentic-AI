"""Operator-configured, bounded third-party scraping providers.

Provider destinations are operator configuration only. Request and response
content never chooses a host, path, or follow-up URL.
"""
from dataclasses import dataclass, field
import json
import os
import threading
import time
from time import monotonic
from urllib.parse import urlparse, urlsplit, urlunsplit

import requests

from app.errors.exceptions import CollectionError
from app.services.collectors.security import validate_url_ssrf, ssrf_safe_connections
from app.services.product_discovery import match_product_identity

_rapidapi_rate_lock = threading.Lock()
_rapidapi_last_request = 0.0


@dataclass
class ScrapingResult:
    status: str
    records: list = field(default_factory=list)
    provider: str = ""
    reason: str = ""
    duration_ms: int = 0


def _record_candidates(value, inherited=None):
    inherited = dict(inherited or {})
    if isinstance(value, list):
        for child in value:
            yield from _record_candidates(child, inherited)
    elif isinstance(value, dict):
        for key in ("product_title", "productTitle", "product_name", "productName", "product", "name"):
            if isinstance(value.get(key), str) and value[key].strip():
                inherited["product_title"] = value[key]
                break
        text_keys = ("review_text", "reviewText", "review", "comment", "body", "text", "review_body")
        if any(isinstance(value.get(key), str) and value[key].strip() for key in text_keys):
            yield {**inherited, **value}
            return
        for child in value.values():
            yield from _record_candidates(child, inherited)


def _provider_source_url(value):
    """Forward product identity without userinfo, query tokens, or fragments."""
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return ""
        host = parts.hostname.encode("idna").decode("ascii")
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme.lower(), host, parts.path[:2048], "", ""))
    except (AttributeError, UnicodeError, ValueError):
        return ""


def normalize_provider_records(payload, entity, requested_url, max_results=100):
    """Extract real review-like records and reject non-matching listings."""
    records, seen = [], set()
    if not isinstance(payload, (dict, list)):
        return records
    for item in _record_candidates(payload):
        text = next((item.get(key) for key in ("review_text", "reviewText", "review", "comment", "body", "text", "review_body")
                     if isinstance(item.get(key), str) and item[key].strip()), "")
        text = " ".join(text.split())[:12000]
        if len(text) < 3:
            continue
        record_id = next((item.get(key) for key in ("review_id", "reviewId", "id", "external_review_id") if item.get(key) is not None), None)
        title = next((item.get(key) for key in ("product_title", "productTitle", "product_name", "productName", "title", "name")
                      if isinstance(item.get(key), str) and item[key].strip()), "")
        url = next((item.get(key) for key in ("review_url", "reviewUrl", "url", "link", "permalink")
                    if isinstance(item.get(key), str) and item[key].strip()), requested_url)
        if record_id is None and not url:
            continue
        product_url = item.get("product_url") or item.get("productUrl") or requested_url
        match = match_product_identity(entity, {**item, "title": title, "product_url": product_url,
                                                "review_text": text, "external_review_id": record_id})
        if not match["matched"]:
            continue
        stable_key = str(record_id or url) + ":" + text.casefold()[:160]
        if stable_key in seen:
            continue
        seen.add(stable_key)
        records.append({
            "external_review_id": str(record_id)[:255] if record_id is not None else None,
            "review_text": text,
            "reviewer_name": item.get("reviewer_name") or item.get("author") or item.get("reviewer"),
            "rating": item.get("rating") or item.get("stars"),
            "review_date": item.get("review_date") or item.get("date") or item.get("created_at"),
            "review_url": url,
            "source_metadata": {
                "productTitle": str(title)[:300] if title else None,
                "productUrl": str(product_url)[:2048] if product_url else None,
                "identityMatch": match,
                "collection": {"level": 2, "method": "third_party_scraping_api"},
            },
        })
        if len(records) >= max(1, min(int(max_results), 500)):
            break
    return records


class RapidAPIScrapingProvider:
    """Generic RapidAPI adapter; endpoint behavior is operator-configured."""

    name = "rapidapi"

    def __init__(self, *, api_key=None, host=None, base_url=None, endpoint=None,
                 source_types=None, timeout=30, max_results=100, request_delay_seconds=0, enabled=True):
        self.api_key = api_key if api_key is not None else os.environ.get("SCRAPING_RAPIDAPI_KEY", "")
        self.host = host if host is not None else os.environ.get("SCRAPING_RAPIDAPI_HOST", "")
        self.base_url = (base_url if base_url is not None else os.environ.get("SCRAPING_RAPIDAPI_BASE_URL", "")).rstrip("/")
        self.endpoint = endpoint if endpoint is not None else os.environ.get("SCRAPING_RAPIDAPI_ENDPOINT", "")
        configured_types = source_types if source_types is not None else os.environ.get("SCRAPING_RAPIDAPI_SOURCE_TYPES", "ecommerce")
        if isinstance(configured_types, (tuple, list, set)):
            configured_types = ",".join(str(item) for item in configured_types)
        self.source_types = {item.strip().casefold() for item in configured_types.split(",") if item.strip()}
        self.timeout = max(1, min(int(timeout), 30))
        self.max_results = max(1, min(int(max_results), 500))
        self.request_delay_seconds = max(0.0, min(float(request_delay_seconds), 60.0))
        self.enabled = bool(enabled)

    def is_available(self):
        if not self.enabled or not all((self.api_key, self.host, self.base_url, self.endpoint)):
            return False
        try:
            parsed = urlparse(self.base_url)
            return (parsed.scheme == "https" and (parsed.hostname or "").casefold() == self.host.casefold()
                    and not parsed.username and not parsed.password and "?" not in self.endpoint and "#" not in self.endpoint)
        except ValueError:
            return False

    def supports(self, source):
        return source.type.casefold() in self.source_types

    def collect(self, source, entity, search_terms):
        started = monotonic()
        if not self.is_available() or not self.supports(source):
            return ScrapingResult("unavailable", provider=self.name, reason="provider_not_configured_or_source_unsupported")
        global _rapidapi_last_request
        with _rapidapi_rate_lock:
            wait_seconds = self.request_delay_seconds - (monotonic() - _rapidapi_last_request)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            _rapidapi_last_request = monotonic()
        path = "/" + self.endpoint.strip("/")
        destination = self.base_url + path
        try:
            validate_url_ssrf(destination)
            with ssrf_safe_connections():
                response = requests.get(
                    destination,
                    headers={"X-RapidAPI-Key": self.api_key, "X-RapidAPI-Host": self.host},
                    params={
                        "query": (search_terms[0] if search_terms else entity.get("canonicalName", ""))[:200],
                        "url": _provider_source_url(source.url),
                        "source": source.type,
                        "max_results": self.max_results,
                    },
                    timeout=self.timeout,
                    allow_redirects=False,
                    stream=True,
                )
        except CollectionError:
            raise
        except requests.Timeout:
            return ScrapingResult("timeout", provider=self.name, reason="provider_timeout", duration_ms=int((monotonic() - started) * 1000))
        except requests.RequestException:
            return ScrapingResult("unavailable", provider=self.name, reason="provider_network_error", duration_ms=int((monotonic() - started) * 1000))

        try:
            if response.status_code in (401, 403):
                return ScrapingResult("authentication_failed", provider=self.name, reason="provider_authentication_failed", duration_ms=int((monotonic() - started) * 1000))
            if response.status_code == 429:
                return ScrapingResult("rate_limited", provider=self.name, reason="provider_rate_limited", duration_ms=int((monotonic() - started) * 1000))
            if response.status_code < 200 or response.status_code >= 300:
                return ScrapingResult("http_error", provider=self.name, reason="provider_http_error", duration_ms=int((monotonic() - started) * 1000))
            chunks, size = [], 0
            for chunk in response.iter_content(8192):
                size += len(chunk)
                if size > 5 * 1024 * 1024:
                    return ScrapingResult("invalid_response", provider=self.name, reason="provider_response_too_large", duration_ms=int((monotonic() - started) * 1000))
                chunks.append(chunk)
            try:
                payload = json.loads(b"".join(chunks).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return ScrapingResult("invalid_response", provider=self.name, reason="provider_invalid_json", duration_ms=int((monotonic() - started) * 1000))
        finally:
            response.close()

        records = normalize_provider_records(payload, entity, source.url, self.max_results)
        records = [record for record in records if not self.api_key or self.api_key not in record.get("review_text", "")]
        for record in records:
            record["source_metadata"]["provider"] = self.name
        return ScrapingResult("success" if records else "no_usable_evidence", records, self.name,
                              duration_ms=int((monotonic() - started) * 1000))


def configured_scraping_providers():
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            config = current_app.config
            return [RapidAPIScrapingProvider(
                api_key=config.get("SCRAPING_RAPIDAPI_KEY", ""),
                host=config.get("SCRAPING_RAPIDAPI_HOST", ""),
                base_url=config.get("SCRAPING_RAPIDAPI_BASE_URL", ""),
                endpoint=config.get("SCRAPING_RAPIDAPI_ENDPOINT", ""),
                source_types=config.get("SCRAPING_RAPIDAPI_SOURCE_TYPES", "ecommerce"),
                timeout=config.get("COLLECTION_REQUEST_TIMEOUT_SECONDS", 30),
                max_results=config.get("COLLECTION_MAX_RESULTS_PER_SOURCE", 100),
                request_delay_seconds=config.get("SCRAPING_RAPIDAPI_REQUEST_DELAY_SECONDS", 1),
                enabled=config.get("SCRAPING_RAPIDAPI_ENABLED", False),
            )]
    except RuntimeError:
        pass
    return [RapidAPIScrapingProvider()]
