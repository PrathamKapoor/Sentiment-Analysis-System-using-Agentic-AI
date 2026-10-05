import json
from types import SimpleNamespace

import pytest

from app.errors.exceptions import CollectionError
from app.services.collectors.base import CollectionLimits
from app.services.collectors.github_issues import GitHubIssuesCollector


def _limits():
    return CollectionLimits(
        timeout_seconds=5, request_delay_seconds=0, max_pages=2,
        max_records=50, max_response_mb=1, max_retries=0,
        max_redirects=0, user_agent="SentimentAnalysisSystem/test",
    )


class _Response:
    def __init__(self, payload, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {"Content-Type": "application/json"}
        self.body = json.dumps(payload).encode()
        self.encoding = "utf-8"
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        self.closed = True


def test_collects_public_repository_issues_without_pull_requests_or_author_names(monkeypatch):
    calls = []
    payload = [
        {
            "id": 991, "number": 17, "title": "App crashes on export",
            "body": "Export fails after selecting CSV.",
            "html_url": "https://github.com/acme/app/issues/17",
            "created_at": "2026-09-01T12:30:00Z", "state": "open",
            "user": {"login": "unnecessary-personal-id"},
            "labels": [{"name": "bug"}],
        },
        {"id": 992, "number": 18, "title": "A pull request", "body": "Not feedback.",
         "pull_request": {"url": "https://api.github.com/repos/acme/app/pulls/18"}},
    ]

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(payload)

    monkeypatch.setattr("app.services.collectors.github_issues.requests.get", fake_get)
    collector = GitHubIssuesCollector(_limits())
    result = collector.collect(SimpleNamespace(url="https://github.com/acme/app"))

    assert len(result.records) == 1
    record = result.records[0]
    assert record["external_review_id"] == "991"
    assert record["review_text"] == "App crashes on export\n\nExport fails after selecting CSV."
    assert record["review_url"] == "https://github.com/acme/app/issues/17"
    assert record["review_date"] == "2026-09-01T12:30:00Z"
    assert "unnecessary-personal-id" not in json.dumps(record)
    assert record["source_metadata"]["state"] == "open"
    assert "api.github.com/repos/acme/app/issues" in calls[0][0]
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["headers"]["X-GitHub-Api-Version"] == "2026-03-10"


def test_rejects_non_github_repository_urls_without_fetching(monkeypatch):
    called = False

    def fake_get(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("must reject before network")

    monkeypatch.setattr("app.services.collectors.github_issues.requests.get", fake_get)
    collector = GitHubIssuesCollector(_limits())
    for url in (
        "https://github.com.evil.test/acme/app",
        "https://user@github.com/acme/app",
        "https://github.com/acme/app/issues/1?url=https://evil.test",
        "http://github.com/acme/app",
    ):
        with pytest.raises(CollectionError):
            collector.validate_source(SimpleNamespace(url=url))
    assert called is False


def test_maps_github_rate_limit_to_stable_collection_status(monkeypatch):
    monkeypatch.setattr(
        "app.services.collectors.github_issues.requests.get",
        lambda *args, **kwargs: _Response({"message": "API rate limit exceeded"}, 403,
                                          {"X-RateLimit-Remaining": "0", "Content-Type": "application/json"}),
    )
    collector = GitHubIssuesCollector(_limits())
    with pytest.raises(CollectionError) as caught:
        collector.collect(SimpleNamespace(url="https://github.com/acme/app"))
    assert caught.value.code == "COLLECTION_RATE_LIMITED"
