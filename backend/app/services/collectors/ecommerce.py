"""Compliance-aware static HTML adapters for public ecommerce reviews."""
import logging
import re
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.errors.exceptions import CollectionError
from app.services.collectors.base import CollectorResult, normalized_record
from app.services.collectors.robots import is_collection_allowed_by_robots
from app.services.collectors.static_html import StaticHTMLCollector, _first, _parse_rating, _text_or_none


_AMAZON_ASIN = re.compile(r"/(?:dp|gp/product|product-reviews)/([A-Z0-9]{10})(?:[/?]|$)", re.I)
_FLIPKART_ITEM = re.compile(r"/(?:p|product-reviews)/(itm[a-z0-9]+)(?:[/?]|$)", re.I)
logger = logging.getLogger(__name__)


def _hostname(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def normalize_ecommerce_url(url):
    """Strip tracking while retaining the stable public product identity."""
    parsed = urlparse(url.strip())
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    scheme = parsed.scheme.lower() or "https"
    if hostname == "amazon.in":
        match = _AMAZON_ASIN.search(parsed.path)
        if match:
            return f"{scheme}://www.amazon.in/dp/{match.group(1).upper()}"
    if hostname == "flipkart.com":
        path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/")
        if _FLIPKART_ITEM.search(path):
            product_path = re.sub(r"/product-reviews/", "/p/", path, count=1)
            identity_query = [
                (key, value) for key, value in parse_qsl(parsed.query)
                if key.lower() in {"pid", "lid"}
            ]
            return urlunparse((scheme, "www.flipkart.com", product_path, "", urlencode(identity_query), ""))
    return url.strip()


class EcommerceAdapter:
    name = "generic_ecommerce"

    @classmethod
    def recognizes(cls, url):
        return True

    def canonical_url(self, url):
        return normalize_ecommerce_url(url)

    def review_url(self, url):
        return self.canonical_url(url)

    def product_identity(self, url):
        return None

    def discover_review_url(self, html, product_url):
        return None

    def classify_html(self, html, final_url=None):
        if self.is_blocked(html):
            return "BLOCKED"
        return "SUCCESS"

    def extract(self, html, max_records):
        return [], 0, _text_or_none(BeautifulSoup(html, "html.parser").title)

    def is_blocked(self, html):
        soup = BeautifulSoup(html, "html.parser")
        title = (_text_or_none(soup.title) or "").casefold()
        visible = soup.get_text(" ", strip=True).casefold()[:4000]
        return any(term in title or term in visible for term in (
            "verify you are human", "captcha", "robot check", "access denied",
        ))

    def next_page(self, html, current_url):
        return None


class AmazonIndiaAdapter(EcommerceAdapter):
    name = "amazon_india"

    @classmethod
    def recognizes(cls, url):
        return _hostname(url) == "amazon.in"

    def review_url(self, url):
        asin = self.product_identity(url)
        if not asin:
            raise CollectionError(
                "This Amazon URL does not contain a recognizable product ASIN.",
                code="COLLECTION_UNSUPPORTED_SOURCE",
            )
        return f"https://www.amazon.in/product-reviews/{asin}"

    def product_identity(self, url):
        match = _AMAZON_ASIN.search(urlparse(url).path)
        return match.group(1).upper() if match else None

    def discover_review_url(self, html, product_url):
        """Find Amazon's own public review link and retain the same ASIN.

        Amazon varies the slug/query around this link, so the product page is
        authoritative. Cross-domain and mismatched-product links are ignored.
        """
        expected_asin = self.product_identity(product_url)
        soup = BeautifulSoup(html, "html.parser")
        selectors = (
            "a[data-hook='see-all-reviews-link-foot'][href]",
            "a[data-hook='see-all-reviews-link'][href]",
            "a[href*='/product-reviews/'][href]",
        )
        for selector in selectors:
            for link in soup.select(selector):
                candidate = urljoin(product_url, link.get("href", ""))
                if _hostname(candidate) != "amazon.in":
                    continue
                if self.product_identity(candidate) == expected_asin:
                    return candidate
        return None

    def classify_html(self, html, final_url=None):
        if self.is_blocked(html):
            return "CHALLENGE"
        parsed = urlparse(final_url or "")
        soup = BeautifulSoup(html, "html.parser")
        title = (_text_or_none(soup.title) or "").casefold()
        if parsed.path.startswith("/ap/signin") or "amazon sign in" in title:
            return "SIGN_IN"
        return "SUCCESS"

    def is_blocked(self, html):
        soup = BeautifulSoup(html, "html.parser")
        title = (_text_or_none(soup.title) or "").casefold()
        return (
            "robot check" in title
            or soup.select_one("form[action*='validateCaptcha'], #captchacharacters") is not None
            or "enter the characters you see below" in soup.get_text(" ", strip=True).casefold()
        )

    def extract(self, html, max_records):
        soup = BeautifulSoup(html, "html.parser")
        containers = soup.select("[data-hook='review']")
        records = []
        for item in containers[:max_records]:
            records.append(normalized_record(
                external_review_id=item.get("id"),
                review_text=_text_or_none(_first(item, "[data-hook='review-body']")),
                reviewer_name=_text_or_none(_first(item, ".a-profile-name")),
                rating=_parse_rating(_first(item, "[data-hook='review-star-rating'], [data-hook='cmps-review-star-rating']")),
                review_date=_text_or_none(_first(item, "[data-hook='review-date']")),
                source_metadata={"title": _text_or_none(_first(item, "[data-hook='review-title']"))},
            ))
        return records, len(containers), _text_or_none(soup.title)

    def next_page(self, html, current_url):
        soup = BeautifulSoup(html, "html.parser")
        link = soup.select_one("li.a-last:not(.a-disabled) a, a[data-hook='pagination-next']")
        return urljoin(current_url, link["href"]) if link and link.get("href") else None


class FlipkartAdapter(EcommerceAdapter):
    name = "flipkart"

    @classmethod
    def recognizes(cls, url):
        return _hostname(url) == "flipkart.com"

    def review_url(self, url):
        normalized = self.canonical_url(url)
        parsed = urlparse(normalized)
        if not _FLIPKART_ITEM.search(parsed.path):
            raise CollectionError(
                "This Flipkart URL does not contain a recognizable product identity.",
                code="COLLECTION_UNSUPPORTED_SOURCE",
            )
        path = re.sub(r"/p/", "/product-reviews/", parsed.path, count=1)
        return urlunparse(("https", "www.flipkart.com", path, "", parsed.query, ""))

    def product_identity(self, url):
        match = _FLIPKART_ITEM.search(urlparse(url).path)
        return match.group(1).lower() if match else None

    def discover_review_url(self, html, product_url):
        expected_identity = self.product_identity(product_url)
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.select("a[href*='/product-reviews/'][href]"):
            candidate = urljoin(product_url, link.get("href", ""))
            if _hostname(candidate) != "flipkart.com":
                continue
            if self.product_identity(candidate) == expected_identity:
                return candidate
        return None

    def classify_html(self, html, final_url=None):
        return "BLOCKED" if self.is_blocked(html) else "SUCCESS"

    def is_blocked(self, html):
        soup = BeautifulSoup(html, "html.parser")
        title = (_text_or_none(soup.title) or "").casefold()
        visible = soup.get_text(" ", strip=True).casefold()[:2500]
        return (
            "access denied" in title
            or "verify you are human" in visible
            or soup.select_one("form[action*='captcha'], [id*='captcha']") is not None
        )

    def extract(self, html, max_records):
        soup = BeautifulSoup(html, "html.parser")
        containers = self.find_review_cards(soup)
        records = []
        for item in containers[:max_records]:
            current = self._extract_current_card(item)
            if current is not None:
                records.append(current)
                continue

            body = _text_or_none(_first(item, "div.ZmyHeo, div.t-ZTKy, [itemprop='reviewBody'], [itemprop='description']"))
            title = _text_or_none(_first(item, "p.z9E0IG, p._2-N8zT"))
            review_text = body or title
            if not review_text:
                continue
            records.append(normalized_record(
                external_review_id=item.get("id"),
                review_text=review_text,
                reviewer_name=_text_or_none(_first(item, "p._2NsDsF, [itemprop='author']")),
                rating=_parse_rating(_first(item, "div.XQDdHH, div._3LWZlK, [itemprop='ratingValue']")),
                review_date=_text_or_none(_first(item, "time, [itemprop='datePublished']")),
                source_metadata={"title": title},
            ))
        return records, len(containers), _text_or_none(soup.title)

    def find_review_cards(self, soup):
        """Return unique, review-scoped cards from old and current markup.

        Flipkart's current desktop HTML is emitted by React Native Web and
        has generated class names. We use the observed card class pair as a
        narrow fast path, then a structural fallback around the meaningful
        `Review for:` variant row. Every candidate is validated before use,
        preventing broad page divs from becoming reviews.
        """
        selectors = (
            "div.col.EPCmJX",
            "div._27M-vq",
            "[itemtype*='Review']",
            "[itemprop='review']",
            "div.r-w7s2jr.r-1c7gwzm",
        )
        cards = []
        seen = set()

        def add(card):
            if card is None or id(card) in seen or not self._looks_like_review_card(card):
                return
            seen.add(id(card))
            cards.append(card)

        for selector in selectors:
            for card in soup.select(selector):
                add(card)

        for text_node in soup.find_all(string=re.compile(r"^\s*Review\s+for\s*:", re.I)):
            variant_row = text_node.parent
            card = variant_row.parent if variant_row else None
            add(card)
        return cards

    @staticmethod
    def _direct_children(card):
        return [child for child in card.find_all(recursive=False) if getattr(child, "name", None)]

    def _looks_like_review_card(self, card):
        if card.select_one("div.ZmyHeo, div.t-ZTKy, [itemprop='reviewBody'], [itemprop='description']"):
            return True
        children = self._direct_children(card)
        if len(children) < 2:
            return False
        texts = [(_text_or_none(child) or "") for child in children]
        variant_index = next((index for index, value in enumerate(texts) if value.casefold().startswith("review for:")), None)
        if variant_index is None or variant_index == 0:
            return False
        title = texts[0].strip()
        body = next((value.strip() for value in texts[variant_index + 1:] if self._is_review_body_text(value)), "")
        return bool(title or body)

    @staticmethod
    def _is_review_body_text(value):
        text = (value or "").strip()
        folded = text.casefold()
        if not text or folded.startswith("review for:"):
            return False
        if "verified purchase" in folded or re.search(r"[·•]\s*[a-z]{3},?\s+\d{4}", text, re.I):
            return False
        return True

    def _extract_current_card(self, card):
        children = self._direct_children(card)
        texts = [(_text_or_none(child) or "") for child in children]
        variant_index = next((index for index, value in enumerate(texts) if value.casefold().startswith("review for:")), None)
        if variant_index is None or variant_index == 0:
            return None

        title_parts = []
        for node in children[0].find_all(string=True):
            value = " ".join(str(node).split()).strip()
            if not value or value in {"•", "·"} or re.fullmatch(r"[0-5](?:\.\d)?", value):
                continue
            title_parts.append(value)
        title = title_parts[-1] if title_parts else (texts[0].strip() or None)
        body = next((value.strip() for value in texts[variant_index + 1:] if self._is_review_body_text(value)), None)
        review_text = body or title
        if not review_text:
            return None

        rating = _parse_rating(children[0])
        if rating is None:
            star_nodes = children[0].select("div.r-tbmifm")
            rating = float(len(star_nodes)) if 1 <= len(star_nodes) <= 5 else None
        metadata = " ".join(texts[variant_index + 1:])
        date_match = re.search(r"[·•]\s*([A-Z][a-z]{2},?\s+\d{4})", metadata)

        reviewer_name = None
        metadata_row = next((child for child in children[variant_index + 1:] if "verified purchase" in (_text_or_none(child) or "").casefold()), None)
        if metadata_row is not None:
            for node in metadata_row.find_all(string=True):
                value = " ".join(str(node).split()).strip()
                if value and not value.startswith(",") and not value.isdigit() and "verified purchase" not in value.casefold() and not value.startswith("·"):
                    reviewer_name = value
                    break

        return normalized_record(
            review_text=review_text,
            reviewer_name=reviewer_name,
            rating=rating,
            review_date=date_match.group(1) if date_match else None,
            source_metadata={"title": title},
        )

    def next_page(self, html, current_url):
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.select("a[href]"):
            label = (_text_or_none(link) or "").casefold()
            if label in {"next", "next ›", "›"}:
                return urljoin(current_url, link["href"])
        return None


class GenericEcommerceAdapter(EcommerceAdapter):
    pass


def resolve_ecommerce_adapter(url):
    for adapter_class in (AmazonIndiaAdapter, FlipkartAdapter):
        if adapter_class.recognizes(url):
            return adapter_class()
    return GenericEcommerceAdapter()


class EcommerceCollector(StaticHTMLCollector):
    collector_type = "ecommerce_static_html"

    @staticmethod
    def _platform_name(adapter):
        return {
            "amazon_india": "Amazon India",
            "flipkart": "Flipkart",
        }.get(adapter.name, adapter.name.replace("_", " ").title())

    def validate_source(self, source):
        super().validate_source(source)
        adapter = resolve_ecommerce_adapter(source.url)
        if not isinstance(adapter, GenericEcommerceAdapter):
            adapter.review_url(source.url)

    def health_check(self, source):
        adapter = resolve_ecommerce_adapter(source.url)
        if isinstance(adapter, GenericEcommerceAdapter):
            return super().health_check(source)
        try:
            result = self._collect_adapted(source, {"maxPages": 1, "maxRecords": 5})
        except CollectionError as exc:
            details = exc.details or {}
            return {
                "available": False,
                "message": exc.message,
                "diagnosticCode": exc.code,
                "platform": self._platform_name(adapter),
                "adapter": adapter.name,
                "adapterClass": adapter.__class__.__name__,
                "productUrl": adapter.canonical_url(source.url),
                "productIdentity": adapter.product_identity(source.url),
                "productPage": {
                    "status": details.get("productPageStatus"),
                    "httpStatus": details.get("productPageHttpStatus"),
                    "finalUrl": details.get("productPageFinalUrl"),
                    "contentType": details.get("productPageContentType"),
                    "redirectCount": details.get("productPageRedirectCount"),
                },
                "reviewPage": {
                    "status": details.get("reviewPageStatus"),
                    "httpStatus": details.get("reviewPageHttpStatus"),
                    "finalUrl": details.get("reviewPageFinalUrl"),
                    "discoveryMethod": details.get("reviewDiscoveryMethod"),
                    "contentType": details.get("reviewPageContentType"),
                    "redirectCount": details.get("reviewPageRedirectCount"),
                },
                "reviewCandidatesDetected": None,
                "validReviewsParsed": None,
                "parserStatus": details.get("parserStatus", "NOT_REACHED"),
                "pageType": "review_page",
                "keywordFilteringStatus": "NOT_REACHED",
            }
        return {
            "available": True,
            "message": result.result_message or "Source is reachable and its public review page was parsed.",
            "diagnosticCode": result.result_code,
            "platform": self._platform_name(adapter),
            "adapter": result.adapter,
            "adapterClass": adapter.__class__.__name__,
            "productUrl": result.normalized_url,
            "productIdentity": result.product_identity,
            "productPage": {
                "status": result.product_page_status,
                "httpStatus": result.product_page_http_status,
                "finalUrl": result.product_page_final_url,
                "contentType": result.product_page_content_type,
                "redirectCount": result.product_page_redirect_count,
            },
            "reviewPage": {
                "status": result.review_page_status,
                "httpStatus": result.review_page_http_status,
                "finalUrl": result.review_page_final_url,
                "discoveryMethod": result.review_discovery_method,
                "contentType": result.review_page_content_type,
                "redirectCount": result.review_page_redirect_count,
            },
            "reviewCandidatesDetected": result.candidate_items_found,
            "validReviewsParsed": result.items_parsed,
            "parserStatus": result.parser_status,
            "pageType": "review_page",
            "keywordFilteringStatus": "NOT_APPLIED_DURING_TEST",
        }

    def preview(self, source, options=None):
        adapter = resolve_ecommerce_adapter(source.url)
        if isinstance(adapter, GenericEcommerceAdapter):
            return super().preview(source, options)
        result = self._collect_adapted(source, {**(options or {}), "maxPages": 1, "maxRecords": 5})
        return {
            "sourceType": source.type,
            "collectorType": self.collector_type,
            "adapter": result.adapter,
            "normalizedUrl": result.normalized_url,
            "pageTitle": getattr(result, "page_title", None),
            "detectedRecordCountEstimate": len(result.records),
            "candidateItemsFound": result.candidate_items_found,
            "sampleRecords": result.records[:3],
            "detectedFields": [field for field in ("review_text", "reviewer_name", "rating", "review_date") if any(record.get(field) for record in result.records)],
            "warnings": result.warnings,
            "fetchStatus": result.fetch_status,
            "httpStatus": result.http_status,
            "productIdentity": result.product_identity,
            "productPageStatus": result.product_page_status,
            "productPageHttpStatus": result.product_page_http_status,
            "productPageFinalUrl": result.product_page_final_url,
            "productPageContentType": result.product_page_content_type,
            "productPageRedirectCount": result.product_page_redirect_count,
            "reviewPageStatus": result.review_page_status,
            "reviewPageHttpStatus": result.review_page_http_status,
            "reviewPageFinalUrl": result.review_page_final_url,
            "reviewPageContentType": result.review_page_content_type,
            "reviewPageRedirectCount": result.review_page_redirect_count,
            "reviewDiscoveryMethod": result.review_discovery_method,
            "parserStatus": result.parser_status,
            "pageType": "review_page",
            "keywordFilteringStatus": "NOT_APPLIED_DURING_PREVIEW",
        }

    def collect(self, source, options=None):
        adapter = resolve_ecommerce_adapter(source.url)
        if isinstance(adapter, GenericEcommerceAdapter):
            result = super().collect(source, options)
            result.adapter = adapter.name
            result.normalized_url = adapter.canonical_url(source.url)
            return result
        return self._collect_adapted(source, options or {})

    def _collect_adapted(self, source, options):
        adapter = resolve_ecommerce_adapter(source.url)
        normalized_url = adapter.canonical_url(source.url)
        product_identity = adapter.product_identity(normalized_url)
        session = self._session()
        result = CollectorResult(
            adapter=adapter.name,
            normalized_url=normalized_url,
            product_identity=product_identity,
        )

        product_html = self._fetch_stage(
            session, normalized_url, adapter, "product", result,
        )
        discovered_url = adapter.discover_review_url(product_html, result.product_page_final_url or normalized_url)
        if discovered_url:
            review_url = discovered_url
            result.review_discovery_method = "product_page_link"
        else:
            review_url = adapter.review_url(normalized_url)
            result.review_discovery_method = "canonical_fallback"
        result.review_target_url = review_url

        logger.info(
            "Ecommerce target: original=%s normalized=%s identity=%s adapter=%s "
            "method=GET target=%s product_status=%s product_final=%s discovery=%s",
            source.url, normalized_url, product_identity, adapter.__class__.__name__,
            review_url, result.product_page_status, result.product_page_final_url,
            result.review_discovery_method,
        )

        allowed, _checked = is_collection_allowed_by_robots(review_url, self.limits)
        if not allowed:
            raise CollectionError(
                "Collection is not permitted for this public review page (robots.txt disallows automated access).",
                code="COLLECTION_NOT_PERMITTED",
                details=self._diagnostic_details(result),
            )

        max_pages = min(options.get("maxPages") or self.limits.max_pages, self.limits.max_pages)
        max_records = min(options.get("maxRecords") or self.limits.max_records, self.limits.max_records)
        page_url = review_url

        for page_number in range(1, max_pages + 1):
            try:
                html = self._fetch_stage(session, page_url, adapter, "review", result)
            except CollectionError as exc:
                if page_number == 1:
                    raise
                result.fetch_status = "partial"
                result.warnings.append(f"Review page {page_number} could not be read: {exc.message}")
                break
            result.fetch_status = "success"
            result.http_status = self._last_http_status
            records, candidates, title = adapter.extract(html, max_records - len(result.records))
            result.page_title = title
            result.records.extend(records)
            result.pages_fetched = page_number
            result.candidate_items_found += candidates
            result.items_parsed += len(records)
            result.items_after_filter += len(records)
            if len(result.records) >= max_records:
                result.truncated = True
                break
            next_url = adapter.next_page(html, page_url)
            if not next_url or not records:
                break
            if _hostname(next_url) != _hostname(page_url):
                result.warnings.append("A cross-domain pagination link was ignored.")
                break
            page_url = next_url
            if page_number < max_pages:
                time.sleep(self.limits.request_delay_seconds)

        if not result.records:
            result.result_code = "COLLECTION_NO_REVIEWS_FOUND"
            result.result_message = "The review page loaded successfully, but no supported review elements were detected."
            result.parser_status = "PARSER_MISMATCH"
            result.warnings.append(result.result_message)
        elif result.fetch_status == "partial":
            result.result_code = "COLLECTION_PARTIAL"
            result.result_message = f"{len(result.records)} review candidates were parsed; one or more later pages could not be read."
            result.parser_status = "SUCCESS"
        else:
            result.result_code = "COLLECTION_SUCCESS"
            result.result_message = f"{len(result.records)} review candidates were parsed."
            result.parser_status = "SUCCESS"
        return result

    def _fetch_stage(self, session, url, adapter, stage, result):
        """Fetch and classify one ecommerce pipeline stage.

        Only safe, bounded diagnostics are attached to public errors. Response
        bodies are never logged or returned.
        """
        platform = self._platform_name(adapter)
        try:
            html = self._fetch_html(url, session)
        except CollectionError as exc:
            status = self._status_for_error(exc)
            self._set_stage(result, stage, status)
            details = self._diagnostic_details(result)
            details.update(exc.details or {})
            logger.info(
                "Ecommerce response: adapter=%s stage=%s method=GET target=%s final=%s "
                "status=%s content_type=%s redirects=%s classification=%s",
                adapter.__class__.__name__, stage, url, self._last_final_url,
                self._last_http_status, self._last_content_type,
                self._last_redirect_count, status,
            )
            if self._last_http_status == 404:
                if stage == "product":
                    raise CollectionError(
                        f"{platform} product page was not found.",
                        code="COLLECTION_HTTP_ERROR",
                        details=details,
                    ) from exc
                raise CollectionError(
                    f"{platform} product page was found, but its public review page could not be found.",
                    code="COLLECTION_HTTP_ERROR",
                    details=details,
                ) from exc
            if exc.code == "COLLECTION_BLOCKED":
                raise CollectionError(
                    f"{platform} blocked the {stage} page collection request.",
                    code=exc.code,
                    details=details,
                ) from exc
            exc.details = details
            raise

        classification = adapter.classify_html(html, self._last_final_url)
        self._set_stage(result, stage, classification)
        logger.info(
            "Ecommerce response: adapter=%s stage=%s method=GET target=%s final=%s "
            "status=%s content_type=%s redirects=%s classification=%s",
            adapter.__class__.__name__, stage, url, self._last_final_url,
            self._last_http_status, self._last_content_type,
            self._last_redirect_count, classification,
        )
        if classification in {"BLOCKED", "CHALLENGE", "SIGN_IN"}:
            raise CollectionError(
                f"{platform} returned a {classification.lower().replace('_', ' ')} page during the {stage} page request.",
                code="COLLECTION_BLOCKED",
                details=self._diagnostic_details(result),
            )
        return html

    def _set_stage(self, result, stage, status):
        setattr(result, f"{stage}_page_status", status)
        setattr(result, f"{stage}_page_http_status", self._last_http_status)
        setattr(result, f"{stage}_page_final_url", self._last_final_url)
        setattr(result, f"{stage}_page_content_type", self._last_content_type)
        setattr(result, f"{stage}_page_redirect_count", self._last_redirect_count)
        if status in {"BLOCKED", "CHALLENGE", "SIGN_IN"}:
            result.fetch_status = "blocked"
        elif status in {"HTTP_404", "NETWORK_ERROR", "TIMEOUT"}:
            result.fetch_status = "failed"
        elif stage == "product":
            result.fetch_status = "product_fetched"
        elif stage == "review":
            result.fetch_status = "success"

    @staticmethod
    def _status_for_error(exc):
        if getattr(exc, "details", {}).get("httpStatus") == 404:
            return "HTTP_404"
        if exc.code == "COLLECTION_BLOCKED":
            return "BLOCKED"
        if exc.code == "COLLECTION_TIMEOUT":
            return "TIMEOUT"
        return "NETWORK_ERROR"

    @staticmethod
    def _diagnostic_details(result):
        return {
            "fetchStatus": result.fetch_status,
            "httpStatus": result.review_page_http_status or result.product_page_http_status,
            "adapter": result.adapter,
            "adapterClass": {
                "amazon_india": "AmazonIndiaAdapter",
                "flipkart": "FlipkartAdapter",
            }.get(result.adapter, "GenericEcommerceAdapter"),
            "normalizedUrl": result.normalized_url,
            "productIdentity": result.product_identity,
            "productPageStatus": result.product_page_status,
            "productPageHttpStatus": result.product_page_http_status,
            "productPageFinalUrl": result.product_page_final_url,
            "productPageContentType": result.product_page_content_type,
            "productPageRedirectCount": result.product_page_redirect_count,
            "reviewPageStatus": result.review_page_status,
            "reviewPageHttpStatus": result.review_page_http_status,
            "reviewPageFinalUrl": result.review_page_final_url,
            "reviewPageContentType": result.review_page_content_type,
            "reviewPageRedirectCount": result.review_page_redirect_count,
            "reviewTargetUrl": result.review_target_url,
            "reviewDiscoveryMethod": result.review_discovery_method,
            "parserStatus": result.parser_status or "NOT_REACHED",
            "httpMethod": "GET",
        }
