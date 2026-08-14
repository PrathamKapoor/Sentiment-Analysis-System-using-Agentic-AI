"""Generic static-HTML collector: requests + BeautifulSoup only (no
Playwright/Selenium — this project only reaches for a real browser engine
when a page genuinely can't be read from raw HTML, which none of Phase 6's
supported source types require). Covers review_site/ecommerce/forum/blog/
news/survey — one class, not one-per-type, since they differ only in which
CSS selectors happen to match, and selectors are data (see below), not
behaviour.

Selectors are never persisted (the approved data_sources schema has no
column for them — see docs/phase6_deferred_issues.md). A caller may pass an
explicit selector override for one preview/collect call via `options`;
otherwise a small set of built-in heuristics (schema.org markup, then
common review/comment class-name patterns) is tried in order. Selectors are
plain CSS strings evaluated via BeautifulSoup .select() — never
executable code, per the "selectors are data, not code" rule.
"""
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.errors.exceptions import CollectionError
from app.services.collectors.base import BaseCollector, normalized_record, CollectorResult
from app.services.collectors.security import validate_url_ssrf, ssrf_safe_connections

_RETRYABLE_5XX = {500, 502, 503, 504}

# Tried in order; first selector set that matches >=1 container wins.
_HEURISTIC_SELECTORS = [
    {
        "review_container_selector": "[itemtype*='Review'], [itemprop='review']",
        "review_text_selector": "[itemprop='reviewBody'], [itemprop='description']",
        "reviewer_selector": "[itemprop='author']",
        "rating_selector": "[itemprop='ratingValue']",
        "date_selector": "[itemprop='datePublished']",
    },
    {
        "review_container_selector": ".review, .comment, .feedback-item, li.review",
        "review_text_selector": ".review-text, .comment-text, .body, p",
        "reviewer_selector": ".reviewer, .author, .username",
        "rating_selector": ".rating, .stars, [data-rating]",
        "date_selector": ".date, time",
    },
]


def _text_or_none(el):
    if el is None:
        return None
    text = el.get_text(strip=True)
    return text or None


def _first(soup_or_el, selector):
    if not selector:
        return None
    try:
        return soup_or_el.select_one(selector)
    except Exception:
        return None


def _parse_rating(el):
    text = _text_or_none(el)
    if not text:
        return None
    import re
    match = re.search(r"[\d.]+", text)
    if not match:
        return None
    try:
        value = float(match.group())
    except ValueError:
        return None
    return value if 0 <= value <= 5 else None


class StaticHTMLCollector(BaseCollector):
    collector_type = "static_html"

    def __init__(self, limits):
        super().__init__(limits)
        self._last_http_status = None
        self._last_final_url = None
        self._last_content_type = None
        self._last_redirect_count = 0

    @classmethod
    def capabilities(cls):
        return {
            "collectorType": cls.collector_type,
            "available": True,
            "unavailableReason": None,
            "supportsPreview": True,
            "supportsPagination": True,
            "requiresCredentials": False,
        }

    def _session(self):
        session = requests.Session()
        session.headers.update({
            "User-Agent": self.limits.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.8",
        })
        return session

    def _response_details(self, fetch_status="failed"):
        return {
            "fetchStatus": fetch_status,
            "httpStatus": self._last_http_status,
            "finalUrl": self._last_final_url,
            "contentType": self._last_content_type,
            "redirectCount": self._last_redirect_count,
            "httpMethod": "GET",
        }

    def _get_with_retries(self, session, url):
        """One URL, retrying only safe transient failures (timeout, 429 with
        Retry-After, transient 5xx) up to max_retries. Never retries 401/403
        or other 4xx. Bounded strictly by max_retries — independent of the
        redirect-hop budget in _fetch_html.
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                with ssrf_safe_connections():
                    resp = session.get(
                        url, timeout=self.limits.timeout_seconds, allow_redirects=False, stream=True,
                    )
            except requests.Timeout:
                if attempt <= self.limits.max_retries:
                    time.sleep(self.limits.request_delay_seconds)
                    continue
                raise CollectionError("The source took too long to respond.", code="COLLECTION_TIMEOUT")
            except requests.RequestException:
                raise CollectionError("Could not reach the source URL.", code="COLLECTION_HTTP_ERROR")

            if resp.status_code == 429 and attempt <= self.limits.max_retries:
                retry_after = resp.headers.get("Retry-After")
                resp.close()
                if not retry_after:
                    raise CollectionError("The source is rate-limiting requests.", code="COLLECTION_RATE_LIMITED")
                try:
                    delay = min(float(retry_after), 10)
                except ValueError:
                    delay = self.limits.request_delay_seconds
                time.sleep(delay)
                continue

            if resp.status_code in _RETRYABLE_5XX and attempt <= self.limits.max_retries:
                resp.close()
                time.sleep(self.limits.request_delay_seconds)
                continue

            return resp

    def _read_body(self, resp):
        if resp.status_code == 429:
            resp.close()
            raise CollectionError("The source is rate-limiting requests.", code="COLLECTION_RATE_LIMITED")
        if resp.status_code == 403:
            resp.close()
            raise CollectionError(
                "The source website blocked the collection request.",
                code="COLLECTION_BLOCKED",
                details=self._response_details("blocked"),
            )
        if resp.status_code == 401:
            resp.close()
            raise CollectionError(
                "The source rejected the request (authentication/authorization required).",
                code="COLLECTION_HTTP_ERROR", details=self._response_details(),
            )
        if resp.status_code >= 400:
            resp.close()
            raise CollectionError(
                f"The source returned HTTP {resp.status_code}.",
                code="COLLECTION_HTTP_ERROR", details=self._response_details(),
            )

        max_bytes = int(self.limits.max_response_mb * 1024 * 1024)
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            resp.close()
            raise CollectionError("The source response was too large.", code="COLLECTION_RESPONSE_TOO_LARGE")

        content_type = resp.headers.get("Content-Type", "")
        if content_type and "html" not in content_type and "xml" not in content_type:
            resp.close()
            raise CollectionError("The source did not return an HTML page.", code="COLLECTION_PARSE_ERROR")

        chunks = []
        total = 0
        for chunk in resp.iter_content(8192):
            total += len(chunk)
            if total > max_bytes:
                resp.close()
                raise CollectionError("The source response was too large.", code="COLLECTION_RESPONSE_TOO_LARGE")
            chunks.append(chunk)
        resp.close()
        try:
            return b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
        except Exception:
            raise CollectionError("Could not decode the source response.", code="COLLECTION_PARSE_ERROR")

    def _fetch_html(self, url, session):
        """Fetches one logical page: SSRF-validates every redirect hop
        (bounded by max_redirects), retries transient failures per hop
        (bounded by max_retries), and enforces the response-size cap.
        """
        current_url = url
        self._last_final_url = url
        self._last_redirect_count = 0
        self._last_content_type = None
        validate_url_ssrf(current_url)

        for hop in range(self.limits.max_redirects + 1):
            resp = self._get_with_retries(session, current_url)
            self._last_http_status = resp.status_code
            self._last_final_url = current_url
            self._last_content_type = resp.headers.get("Content-Type", "")
            self._last_redirect_count = hop

            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                resp.close()
                if not location:
                    raise CollectionError("Redirect response had no Location header.", code="COLLECTION_HTTP_ERROR")
                current_url = urljoin(current_url, location)
                validate_url_ssrf(current_url)  # re-check every hop — blocks redirect-based SSRF
                continue

            return self._read_body(resp)

        raise CollectionError("Too many redirects.", code="COLLECTION_HTTP_ERROR")

    def health_check(self, source):
        try:
            validate_url_ssrf(source.url)
        except CollectionError as exc:
            return {"available": False, "message": exc.message}
        try:
            session = self._session()
            self._fetch_html(source.url, session)
        except CollectionError as exc:
            return {"available": False, "message": exc.message}
        return {"available": True, "message": "Source is reachable."}

    def validate_source(self, source):
        validate_url_ssrf(source.url)

    def _select_records(self, soup, selectors):
        containers = []
        try:
            containers = soup.select(selectors["review_container_selector"])
        except Exception:
            containers = []
        return containers

    def _pick_selectors(self, soup, explicit_selectors):
        if explicit_selectors and explicit_selectors.get("review_container_selector"):
            return explicit_selectors
        for candidate in _HEURISTIC_SELECTORS:
            if self._select_records(soup, candidate):
                return candidate
        return None

    def _extract(self, html, selectors, max_records):
        soup = BeautifulSoup(html, "html.parser")
        chosen = self._pick_selectors(soup, selectors)
        page_title = _text_or_none(soup.select_one("title"))
        if chosen is None:
            return [], page_title, chosen, 0

        records = []
        containers = self._select_records(soup, chosen)
        for container in containers[:max_records]:
            text_el = _first(container, chosen.get("review_text_selector"))
            text = _text_or_none(text_el) or _text_or_none(container)
            # A matched container with no extractable text is still a
            # detected record (review_text=None, never fabricated) — the
            # ingestion layer's existing clean_text() check is what marks it
            # invalid, so "invalid" is counted in exactly one place.
            records.append(normalized_record(
                review_text=text,
                reviewer_name=_text_or_none(_first(container, chosen.get("reviewer_selector"))),
                rating=_parse_rating(_first(container, chosen.get("rating_selector"))),
                review_date=_text_or_none(_first(container, chosen.get("date_selector"))),
                source_metadata={},
            ))
        return records, page_title, chosen, len(containers)

    def preview(self, source, options=None):
        options = options or {}
        session = self._session()
        html = self._fetch_html(source.url, session)
        records, page_title, chosen, candidates = self._extract(html, options.get("selectors"), max_records=5)

        warnings = []
        if chosen is None:
            warnings.append("No review-like content could be detected on this page with the built-in heuristics.")
        elif not any(r.get("review_text") for r in records):
            warnings.append("Matching containers were found but none had extractable text.")

        return {
            "sourceType": source.type,
            "collectorType": self.collector_type,
            "pageTitle": page_title,
            "detectedRecordCountEstimate": len(records),
            "candidateItemsFound": candidates,
            "fetchStatus": "success",
            "httpStatus": self._last_http_status,
            "sampleRecords": records[:3],
            "detectedFields": [f for f in ("review_text", "reviewer_name", "rating", "review_date") if any(r.get(f) for r in records)],
            "warnings": warnings,
        }

    def collect(self, source, options=None):
        options = options or {}
        session = self._session()
        result = CollectorResult()
        max_pages = min(options.get("maxPages") or self.limits.max_pages, self.limits.max_pages)
        max_records = min(options.get("maxRecords") or self.limits.max_records, self.limits.max_records)

        page_url = source.url
        consecutive_failures = 0
        for page_num in range(1, max_pages + 1):
            try:
                html = self._fetch_html(page_url, session)
            except CollectionError:
                consecutive_failures += 1
                if consecutive_failures >= 2 or page_num == 1:
                    raise
                break  # stop paginating after a later page fails repeatedly, keep what we have

            consecutive_failures = 0
            records, _title, chosen, candidates = self._extract(
                html, options.get("selectors"), max_records=max_records - len(result.records)
            )
            result.records.extend(records)
            result.pages_fetched = page_num
            result.fetch_status = "success"
            result.http_status = self._last_http_status
            result.candidate_items_found += candidates
            result.items_parsed += len(records)
            result.items_after_filter += len(records)

            if chosen is None or not records:
                break
            if len(result.records) >= max_records:
                result.truncated = True
                break

            next_link = self._find_next_page(html, page_url)
            if not next_link:
                break
            page_url = next_link
            if page_num < max_pages:
                time.sleep(self.limits.request_delay_seconds)
        else:
            # loop ran to completion without an early `break` — max_pages was hit
            # while more pages were still available.
            if result.pages_fetched >= max_pages:
                result.truncated = True

        result.adapter = self.collector_type
        result.normalized_url = source.url
        if not result.records:
            result.result_code = "COLLECTION_NO_REVIEWS_FOUND"
            result.result_message = "The page loaded successfully, but no supported review elements were found."
            result.warnings.append(result.result_message)
        else:
            result.result_code = "COLLECTION_SUCCESS"
            result.result_message = f"{len(result.records)} review candidates were parsed."
        return result

    def _find_next_page(self, html, current_url):
        soup = BeautifulSoup(html, "html.parser")
        next_el = soup.select_one("a[rel='next'], a.next, a.pagination-next")
        if next_el and next_el.get("href"):
            return urljoin(current_url, next_el["href"])
        return None

    def normalize_record(self, raw):
        return raw  # already normalized by _extract
