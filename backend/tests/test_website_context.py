"""Project website context tests."""
from __future__ import annotations

import io

import pytest

from app.errors.exceptions import CollectionError
from app.services.collectors.security import validate_url_ssrf
from app.services.website_context_service import (
    STATUS_BLOCKED,
    STATUS_FETCH_FAILED,
    STATUS_OK,
    STATUS_TOO_LARGE,
    extract_website_context,
    validate_url,
)


# ---------------- shape / SSRF tests ----------------


def test_validate_url_rejects_empty():
    with pytest.raises(CollectionError):
        validate_url("")


def test_validate_url_rejects_non_http_scheme():
    with pytest.raises(CollectionError):
        validate_url("file:///etc/passwd")
    with pytest.raises(CollectionError):
        validate_url("ftp://example.com/")


def test_validate_url_rejects_loopback():
    with pytest.raises(CollectionError):
        validate_url("http://localhost/")


def test_validate_url_rejects_private_ip_via_dns(monkeypatch):
    import socket
    def fake_getaddrinfo(host, *a, **kw):
        return [(2, 1, 6, "", ("10.0.0.5", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(CollectionError):
        validate_url_ssrf("https://example.com/")


def test_extract_returns_blocked_status_for_loopback(app, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 0))])
    with app.app_context():
        res = extract_website_context("https://example.com/")
    assert res.status == STATUS_BLOCKED


# ---------------- happy path extraction ----------------


def _fake_response(url, html="<html><head><title>Acme</title>"
                  "<meta name='description' content='We sell stuff'>"
                  "</head><body><h1>Welcome</h1>"
                  "<p>" + "x" * 200 + "</p></body></html>"):
    """Build a Response with iter_content that yields the body once.
    We do this by attaching a ``raw`` attribute that ``iter_content``
    can read from.
    """
    import requests
    resp = requests.Response()
    resp.status_code = 200
    resp._content = html.encode("utf-8")
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.url = url
    resp.encoding = "utf-8"
    resp.raw = io.BytesIO(resp._content)
    return resp


def test_extract_happy_path(app, monkeypatch):
    """A public IP, real HTML — extraction returns status ok with the
    expected structured fields."""
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("93.184.216.34", 0))])
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _fake_response("https://example.com/"))
    with app.app_context():
        res = extract_website_context("https://example.com/")
    assert res.status == STATUS_OK
    assert res.title == "Acme"
    assert "We sell stuff" in res.meta_description
    assert "Welcome" in res.headings
    assert res.body_excerpt
    assert res.content_hash and len(res.content_hash) == 64


def test_extract_returns_too_large_status(app, monkeypatch):
    """A response that exceeds the size cap is rejected without buffering
    the full body into memory."""
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("93.184.216.34", 0))])

    class _StreamingResp:
        status_code = 200
        url = "https://example.com/"
        headers = {"Content-Type": "text/html"}
        encoding = "utf-8"

        def __init__(self, total_bytes):
            self._sent = 0
            self._total = total_bytes

        def iter_content(self, chunk_size=64 * 1024):
            chunk = b"x" * chunk_size
            while self._sent < self._total:
                self._sent += chunk_size
                yield chunk

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _StreamingResp(10 * 1024 * 1024))
    with app.app_context():
        res = extract_website_context("https://example.com/", max_bytes=1024)
    assert res.status == STATUS_TOO_LARGE


def test_extract_returns_fetch_failed_on_timeout(app, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("93.184.216.34", 0))])
    import requests
    def _boom(*a, **kw):
        raise requests.Timeout("read timed out")
    monkeypatch.setattr(requests, "get", _boom)
    with app.app_context():
        res = extract_website_context("https://example.com/")
    assert res.status == STATUS_FETCH_FAILED
    assert "timed out" in (res.failure_reason or "").lower()


# ---------------- project website route tests ----------------


def test_set_and_get_website_url(client):
    from tests.conftest_project import owner_context, create_project
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)

    # Initially: no context.
    resp = client.get(f"/api/v1/projects/{project_id}/website/context", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["context"] is None

    # Set a URL (without auto-refresh).
    resp = client.put(
        f"/api/v1/projects/{project_id}/website/context",
        json={"websiteUrl": "https://example.com/", "autoRefresh": False},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["context"]["status"] == "pending"
    assert body["context"]["websiteUrl"] == "https://example.com/"

    # Clear the URL.
    resp = client.put(
        f"/api/v1/projects/{project_id}/website/context",
        json={"websiteUrl": None},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["context"] is None


def test_set_website_url_with_auto_refresh_stubs_extractor(client, monkeypatch):
    """``autoRefresh: true`` should run a single bounded extraction and
    cache the result. We stub the extractor to avoid hitting the
    network and to be deterministic about success."""
    from tests.conftest_project import owner_context, create_project
    from app.services import project_website_service
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    fake_ctx = {
        "projectId": project_id,
        "websiteUrl": "https://example.com/",
        "sourceUrl": "https://example.com/",
        "status": "ok",
        "title": "Acme",
        "metaDescription": "We sell stuff",
        "headings": ["Welcome"],
        "bodyExcerpt": "Welcome to Acme.",
        "contentHash": "x" * 64,
        "failureReason": None,
        "extractedAt": "2026-01-01T00:00:00+00:00",
    }
    monkeypatch.setattr(project_website_service, "refresh_website_context", lambda *a, **kw: fake_ctx)
    resp = client.put(
        f"/api/v1/projects/{project_id}/website/context",
        json={"websiteUrl": "https://example.com/", "autoRefresh": True},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]["context"]
    assert body["status"] == "ok"
    assert body["title"] == "Acme"


def test_cross_tenant_website_context_blocked(client):
    from tests.conftest_project import owner_context, create_project
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.put(
        f"/api/v1/projects/{project_id}/website/context",
        json={"websiteUrl": "https://example.com/"},
        headers=other_headers,
    )
    assert resp.status_code == 404


def test_website_context_invalid_url_rejected(client):
    from tests.conftest_project import owner_context, create_project
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.put(
        f"/api/v1/projects/{project_id}/website/context",
        json={"websiteUrl": "file:///etc/passwd"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_website_context_requires_auth(client):
    resp = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000/website/context")
    assert resp.status_code in (401, 422, 404)


def test_refresh_endpoint_persists_cached_context(client, monkeypatch):
    from tests.conftest_project import owner_context, create_project
    from app.services import project_website_service
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    client.put(
        f"/api/v1/projects/{project_id}/website/context",
        json={"websiteUrl": "https://example.com/"},
        headers=headers,
    )
    fake = {
        "projectId": project_id,
        "websiteUrl": "https://example.com/",
        "sourceUrl": "https://example.com/",
        "status": "ok",
        "title": "T",
        "metaDescription": "M",
        "headings": ["H1"],
        "bodyExcerpt": "B",
        "contentHash": "a" * 64,
        "failureReason": None,
        "extractedAt": "2026-01-01T00:00:00+00:00",
    }
    monkeypatch.setattr(project_website_service, "refresh_website_context", lambda *a, **kw: fake)
    resp = client.post(f"/api/v1/projects/{project_id}/website/context/refresh", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["context"]["status"] == "ok"


def test_refresh_endpoint_404_for_cross_tenant(client):
    from tests.conftest_project import owner_context, create_project
    _, headers = owner_context(client)
    project_id = create_project(client, headers)
    _, other_headers = owner_context(client, org_name="Other Org", email="other2@other.test")
    resp = client.post(f"/api/v1/projects/{project_id}/website/context/refresh", headers=other_headers)
    assert resp.status_code == 404
