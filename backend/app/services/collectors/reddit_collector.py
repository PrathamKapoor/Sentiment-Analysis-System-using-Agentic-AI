"""Public Reddit support — gracefully unavailable without API credentials.

Reddit's own terms require the official API (OAuth client credentials) for
programmatic access; scraping reddit.com's HTML directly is against its
robots.txt and terms, so this collector never falls back to HTML scraping.
Without REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET configured, it reports itself
unavailable via health_check/validate_source rather than failing the whole
Phase 6 build — see docs/phase6_deferred_issues.md.
"""
import os

from app.errors.exceptions import CollectionError
from app.services.collectors.base import BaseCollector, CollectorResult


def _has_credentials():
    return bool(os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET"))


class PublicRedditCollector(BaseCollector):
    collector_type = "reddit_api"

    @classmethod
    def capabilities(cls):
        has_creds = _has_credentials()
        return {
            "collectorType": cls.collector_type,
            "available": False,  # even with credentials, the API client itself isn't implemented — see D6-02
            "unavailableReason": (
                "Reddit API integration is not yet implemented in Phase 6."
                if has_creds else
                "REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET are not configured."
            ),
            "supportsPreview": False,
            "supportsPagination": False,
            "requiresCredentials": True,
        }

    def health_check(self, source):
        if not _has_credentials():
            return {
                "available": False,
                "message": "Reddit collection requires REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET to be "
                            "configured (official API only — this system does not scrape reddit.com "
                            "directly). Upload a dataset export instead until credentials are configured.",
            }
        return {"available": False, "message": "Reddit API integration is not yet implemented in Phase 6."}

    def validate_source(self, source):
        if not _has_credentials():
            raise CollectionError(
                "Reddit collection is not available without configured API credentials. "
                "Use dataset upload instead.",
                code="COLLECTION_UNSUPPORTED_SOURCE",
            )
        raise CollectionError(
            "Reddit API integration is not yet implemented in Phase 6.",
            code="COLLECTION_UNSUPPORTED_SOURCE",
        )

    def preview(self, source, options=None):
        self.validate_source(source)

    def collect(self, source, options=None):
        self.validate_source(source)
        return CollectorResult()

    def normalize_record(self, raw):
        return raw
