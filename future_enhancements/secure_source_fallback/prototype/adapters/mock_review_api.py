from .base import SourceAdapter
from ..errors import CredentialRequiredError, RateLimitError, SourceUnavailableError


class MockReviewApiAdapter(SourceAdapter):
    def __init__(self, mode="success", records=None):
        self.mode, self.records, self.calls = mode, records or [], 0

    def search(self, source, intent):
        self.calls += 1
        if self.mode == "unavailable": raise SourceUnavailableError("source unavailable")
        if self.mode == "rate_limited": raise RateLimitError("rate limited")
        if self.mode == "credentials": raise CredentialRequiredError("credentials required")
        if self.mode == "malformed": return [{"id": "broken", "text": ""}]
        return list(self.records)
