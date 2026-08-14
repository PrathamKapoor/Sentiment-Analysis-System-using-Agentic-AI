"""Adapter interface every source-type collector implements. Each collector
type is isolated (see static_html.py / reddit_collector.py) — this module
only defines the shared contract and the normalized-record shape.
"""
from dataclasses import dataclass, field


NORMALIZED_RECORD_FIELDS = (
    "external_review_id", "review_text", "reviewer_name", "rating",
    "review_date", "review_url", "language", "source_metadata",
)


def normalized_record(**kwargs):
    """Builds the common record shape every collector emits. Unset fields
    are explicitly None — never fabricated, never silently omitted.
    """
    record = {f: None for f in NORMALIZED_RECORD_FIELDS}
    record["source_metadata"] = {}
    for key, value in kwargs.items():
        if key not in NORMALIZED_RECORD_FIELDS:
            raise ValueError(f"Unknown normalized record field: {key}")
        record[key] = value
    return record


@dataclass
class CollectionLimits:
    timeout_seconds: int
    request_delay_seconds: float
    max_pages: int
    max_records: int
    max_response_mb: float
    max_retries: int
    max_redirects: int
    user_agent: str


@dataclass
class CollectorResult:
    records: list = field(default_factory=list)
    pages_fetched: int = 0
    warnings: list = field(default_factory=list)
    truncated: bool = False  # hit max_pages/max_records before the source was exhausted
    fetch_status: str = "not_started"
    http_status: int | None = None
    candidate_items_found: int = 0
    items_parsed: int = 0
    items_after_filter: int = 0
    adapter: str | None = None
    normalized_url: str | None = None
    result_code: str | None = None
    result_message: str | None = None
    product_identity: str | None = None
    product_page_status: str | None = None
    product_page_http_status: int | None = None
    product_page_final_url: str | None = None
    product_page_content_type: str | None = None
    product_page_redirect_count: int = 0
    review_page_status: str | None = None
    review_page_http_status: int | None = None
    review_page_final_url: str | None = None
    review_page_content_type: str | None = None
    review_page_redirect_count: int = 0
    review_target_url: str | None = None
    review_discovery_method: str | None = None
    parser_status: str | None = None


class BaseCollector:
    """Every collector implements these five methods. `source` is a
    DataSource model instance; `limits` is a CollectionLimits built from
    app config (never hard-coded inside a collector).
    """

    collector_type = "base"

    def __init__(self, limits):
        self.limits = limits

    def health_check(self, source):
        """Cheap reachability/compatibility check. Returns
        {"available": bool, "message": str}. Must not raise for an
        ordinary unreachable/incompatible source — only for a genuine
        safety violation (SSRF/invalid URL), which callers should let
        propagate as a CollectionError.
        """
        raise NotImplementedError

    def validate_source(self, source):
        """Raises CollectionError if this collector cannot safely handle
        `source` at all (wrong protocol, missing credentials, etc).
        """
        raise NotImplementedError

    def preview(self, source, options=None):
        """Returns a preview dict (see collection_service.preview_source)
        without ever creating Review rows.
        """
        raise NotImplementedError

    def collect(self, source, options=None):
        """Returns a CollectorResult of normalized records. Never inserts
        into the database itself — that's collection_service's job, so
        dedup/validation stays in one place.
        """
        raise NotImplementedError

    def normalize_record(self, raw):
        raise NotImplementedError

    @classmethod
    def capabilities(cls):
        """Static capability description, independent of any specific
        DataSource row — this is what lets a caller (e.g. Phase 7's
        orchestration) check "can this collector even work at all" before
        touching a real source, so an unavailable collector (Reddit today)
        produces a skip/warning instead of a crash. Per-source reachability
        (is *this* URL actually up right now) is a separate concern — see
        health_check().
        """
        raise NotImplementedError
