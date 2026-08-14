from app.services.collectors.static_html import StaticHTMLCollector
from app.services.collectors.ecommerce import EcommerceCollector
from app.services.collectors.reddit_collector import PublicRedditCollector

# One HTML-scraping adapter covers every type that's just "a web page with
# review-like content" — review_site/ecommerce/forum/blog/news/survey only
# differ in which selector heuristic happens to match, not in behaviour, so
# they share StaticHTMLCollector rather than duplicating near-identical
# classes (see docs/phase6_deferred_issues.md for the reconciliation note).
_REGISTRY = {
    "review_site": StaticHTMLCollector,
    "ecommerce": EcommerceCollector,
    "forum": StaticHTMLCollector,
    "blog": StaticHTMLCollector,
    "news": StaticHTMLCollector,
    "survey": StaticHTMLCollector,
    "reddit": PublicRedditCollector,
}


def get_collector(source_type, limits):
    collector_cls = _REGISTRY.get(source_type)
    if collector_cls is None:
        return None
    return collector_cls(limits)


def describe_source_type(source_type):
    """Structured, static capability info for one source type — usable by a
    caller (e.g. Phase 7 orchestration) to decide skip-vs-attempt *before*
    touching a real source, so an unsupported/unavailable type produces a
    warning, not a crash. Never raises.
    """
    collector_cls = _REGISTRY.get(source_type)
    if collector_cls is None:
        return {
            "sourceType": source_type,
            "collectorType": None,
            "available": False,
            "unavailableReason": f"No collector is registered for source type '{source_type}'.",
            "supportsPreview": False,
            "supportsPagination": False,
            "requiresCredentials": False,
        }
    return {"sourceType": source_type, **collector_cls.capabilities()}


def describe_all_source_types():
    return [describe_source_type(t) for t in _REGISTRY]
