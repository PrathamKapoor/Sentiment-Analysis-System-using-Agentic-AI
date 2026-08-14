"""Phase 6 — web-data collection. No live network access: DNS resolution
and HTTP fetches are both monkeypatched so these tests never depend on the
internet being reachable, per the Phase 6 test requirements.
"""
import socket

import pytest
import requests

from tests.conftest_project import owner_context, create_project

PUBLIC_HTML = """
<html><head><title>Example Reviews</title></head>
<body>
  <div class="review"><p class="review-text">Great product, very happy.</p>
    <span class="reviewer">Alice</span><span class="rating">5</span><time class="date">2026-06-01</time></div>
  <div class="review"><p class="review-text">Terrible delivery experience.</p>
    <span class="reviewer">Bob</span><span class="rating">1</span><time class="date">2026-06-02</time></div>
</body></html>
"""


class _FakeResponse:
    def __init__(self, status_code=200, html="", headers=None):
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self._body = html.encode("utf-8")
        self.encoding = "utf-8"

    def iter_content(self, chunk_size):
        yield self._body

    @property
    def text(self):
        return self._body.decode("utf-8")

    def close(self):
        pass


def _mock_public_dns(monkeypatch, hostnames):
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *a, **kw):
        if host in hostnames:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real_getaddrinfo(host, *a, **kw)

    monkeypatch.setattr("app.services.collectors.security.socket.getaddrinfo", fake_getaddrinfo)


def _mock_get(monkeypatch, responder):
    """responder(url) -> _FakeResponse"""
    def fake_get(self, url, **kwargs):
        return responder(url)

    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(requests, "get", lambda url, **kw: responder(url))  # robots.txt uses requests.get directly


def _create_source(client, headers, project_id, url="https://reviews.example.test/list", type_="review_site"):
    resp = client.post(
        f"/api/v1/projects/{project_id}/sources", json={"type": type_, "url": url}, headers=headers,
    )
    return resp.get_json()["data"]["id"]


def _no_robots(url):
    return _FakeResponse(status_code=404)


# ---------------------------------------------------------------- SOURCE VALIDATION

def test_valid_public_url_source_created(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "review_site", "url": "https://reviews.example.test/list"}, headers=headers,
    )
    assert resp.status_code == 201


def test_invalid_url_rejected_at_creation(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/sources", json={"type": "review_site", "url": "not-a-url"}, headers=headers,
    )
    assert resp.status_code == 400


def test_localhost_rejected_at_creation(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "review_site", "url": "http://localhost/reviews"}, headers=headers,
    )
    assert resp.status_code == 400


def test_unsupported_scheme_rejected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "review_site", "url": "ftp://files.example.test/reviews"}, headers=headers,
    )
    assert resp.status_code == 400


def test_file_scheme_rejected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "review_site", "url": "file:///etc/passwd"}, headers=headers,
    )
    assert resp.status_code == 400


def test_private_ip_blocked_at_collection_time(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id, url="http://192.168.1.50/reviews")

    # test-connection never hard-fails (it's a reachability probe, not a
    # collection attempt) — SSRF-blocked surfaces as available:false, 200.
    resp = client.post(f"/api/v1/sources/{source_id}/test-connection", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["available"] is False

    # collect (the actual data-fetching action) does hard-fail on SSRF.
    collect_resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert collect_resp.status_code == 422
    assert collect_resp.get_json()["error"]["code"] == "COLLECTION_SSRF_BLOCKED"


def test_source_disabled_blocks_collection(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    client.patch(f"/api/v1/sources/{source_id}", json={"enabled": False}, headers=headers)

    resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "COLLECTION_SOURCE_DISABLED"


def test_tenant_isolation_on_collect(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)

    _, other_headers = owner_context(client, org_name="Other Org6", email="other6@other.test")
    resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=other_headers)
    assert resp.status_code == 404


def test_missing_jwt_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)

    resp = client.post(f"/api/v1/sources/{source_id}/collect")
    assert resp.status_code == 401


# ---------------------------------------------------------------- PREVIEW

def test_preview_returns_samples_without_creating_reviews(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)

    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        return _FakeResponse(html=PUBLIC_HTML)
    _mock_get(monkeypatch, responder)

    resp = client.post(f"/api/v1/sources/{source_id}/preview", headers=headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["detectedRecordCountEstimate"] == 2
    assert len(body["sampleRecords"]) == 2
    assert body["collectionAllowed"] is True

    reviews_resp = client.get(f"/api/v1/projects/{project_id}/reviews", headers=headers)
    assert reviews_resp.get_json()["data"]["items"] == []


def test_preview_warns_when_nothing_detected(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        return _FakeResponse(html="<html><body><p>Nothing review-shaped here.</p></body></html>")
    _mock_get(monkeypatch, responder)

    resp = client.post(f"/api/v1/sources/{source_id}/preview", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["warnings"]


# ---------------------------------------------------------------- COLLECTOR / INGESTION

def test_collect_inserts_reviews_linked_to_source(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        return _FakeResponse(html=PUBLIC_HTML)
    _mock_get(monkeypatch, responder)

    resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["recordsFound"] == 2
    assert body["recordsInserted"] == 2
    assert body["recordsDuplicate"] == 0
    assert body["recordsInvalid"] == 0
    assert body["status"] == "completed"

    reviews = client.get(f"/api/v1/projects/{project_id}/reviews", headers=headers).get_json()["data"]["items"]
    assert len(reviews) == 2
    assert all(r["dataSourceId"] == source_id for r in reviews)

    source = client.get(f"/api/v1/projects/{project_id}/sources", headers=headers).get_json()["data"]["items"][0]
    assert source["lastCollectedAt"] is not None


def test_duplicate_detection_across_collection_runs(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        return _FakeResponse(html=PUBLIC_HTML)
    _mock_get(monkeypatch, responder)

    client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    second = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    body = second.get_json()["data"]
    assert body["recordsDuplicate"] == 2
    assert body["recordsInserted"] == 2  # duplicates are inserted+flagged, not rejected (Phase 2 precedent)
    assert body["duplicatesSkipped"] == 0
    assert body["itemsSaved"] == 2

    reviews = client.get(f"/api/v1/projects/{project_id}/reviews", headers=headers).get_json()["data"]["items"]
    assert len(reviews) == 4
    assert sum(1 for r in reviews if r["isDuplicate"]) == 2


def test_invalid_records_skipped(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    html = """
    <html><body>
      <div class="review"><p class="review-text">Valid review text here.</p></div>
      <div class="review"><p class="review-text">   </p></div>
    </body></html>
    """

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        return _FakeResponse(html=html)
    _mock_get(monkeypatch, responder)

    resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    body = resp.get_json()["data"]
    assert body["recordsInserted"] == 1
    assert body["recordsInvalid"] == 1
    assert body["status"] == "partial_success"
    assert body["candidateItemsFound"] == 2
    assert body["itemsParsed"] == 2
    assert body["itemsAfterFilter"] == 2
    assert body["itemsSaved"] == 1


def test_empty_result_reported_not_errored(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        return _FakeResponse(html="<html><body><p>No reviews here.</p></body></html>")
    _mock_get(monkeypatch, responder)

    resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["status"] == "no_records"
    assert body["recordsInserted"] == 0
    assert body["fetchStatus"] == "success"
    assert body["candidateItemsFound"] == 0
    assert body["resultCode"] == "COLLECTION_NO_REVIEWS_FOUND"


def test_timeout_reported_as_collection_timeout(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    def fake_get(self, url, **kwargs):
        raise requests.Timeout("simulated timeout")
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(requests, "get", lambda url, **kw: _no_robots(url))

    resp = client.post(f"/api/v1/sources/{source_id}/test-connection", headers=headers)
    assert resp.status_code == 200  # health_check swallows the error into {"available": False}
    assert resp.get_json()["data"]["available"] is False


def test_http_500_retries_then_fails(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    calls = {"n": 0}

    def fake_get(self, url, **kwargs):
        calls["n"] += 1
        return _FakeResponse(status_code=500)
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(requests, "get", lambda url, **kw: _no_robots(url))

    resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "COLLECTION_HTTP_ERROR"
    assert calls["n"] == 3  # 1 initial + SCRAPER_MAX_RETRIES (default 2) retries, exactly


def test_429_without_retry_after_fails_as_rate_limited(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    def fake_get(self, url, **kwargs):
        return _FakeResponse(status_code=429, headers={})
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(requests, "get", lambda url, **kw: _no_robots(url))

    resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "COLLECTION_RATE_LIMITED"


def test_response_too_large_rejected(client, monkeypatch, app):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})
    app.config["SCRAPER_MAX_RESPONSE_MB"] = 0.00001  # ~10 bytes

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        return _FakeResponse(html=PUBLIC_HTML)  # far bigger than 10 bytes
    _mock_get(monkeypatch, responder)

    resp = client.post(f"/api/v1/sources/{source_id}/test-connection", headers=headers)
    assert resp.get_json()["data"]["available"] is False


def test_malformed_html_does_not_crash(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        return _FakeResponse(html="<html><body><div class='review'><p class='review-text'>Unclosed tag")
    _mock_get(monkeypatch, responder)

    resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert resp.status_code == 200  # BeautifulSoup's html.parser tolerates unclosed tags


# ---------------------------------------------------------------- POLICY / ROBOTS

def test_robots_disallow_blocks_collection(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _FakeResponse(status_code=200, html="User-agent: *\nDisallow: /\n")
        return _FakeResponse(html=PUBLIC_HTML)
    _mock_get(monkeypatch, responder)

    resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "COLLECTION_NOT_PERMITTED"

    from app.models import AuditLog
    actions = {a.action for a in AuditLog.query.filter_by(entity_type="data_source", entity_id=source_id).all()}
    assert "collection.blocked_by_policy" in actions


def test_collector_capabilities_discovery(app):
    from app.services import collection_service

    with app.app_context():
        capabilities = collection_service.get_collector_capabilities()

    by_type = {c["sourceType"]: c for c in capabilities}
    assert by_type["review_site"]["available"] is True
    assert by_type["review_site"]["requiresCredentials"] is False
    assert by_type["reddit"]["available"] is False
    assert by_type["reddit"]["unavailableReason"]
    assert by_type["reddit"]["requiresCredentials"] is True


def test_reddit_source_reports_unavailable_gracefully(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id, url="https://reddit.com/r/example", type_="reddit")

    resp = client.post(f"/api/v1/sources/{source_id}/test-connection", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["available"] is False

    collect_resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert collect_resp.status_code == 422
    assert collect_resp.get_json()["error"]["code"] == "COLLECTION_UNSUPPORTED_SOURCE"


# ---------------------------------------------------------------- STATUS / HISTORY / BULK

def test_collection_status_and_history(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        return _FakeResponse(html=PUBLIC_HTML)
    _mock_get(monkeypatch, responder)

    status_before = client.get(f"/api/v1/sources/{source_id}/collection-status", headers=headers).get_json()["data"]
    assert status_before["hasEverCollected"] is False

    client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)

    status_after = client.get(f"/api/v1/sources/{source_id}/collection-status", headers=headers).get_json()["data"]
    assert status_after["hasEverCollected"] is True
    assert status_after["lastAction"] == "collection.completed"

    history = client.get(f"/api/v1/sources/{source_id}/collection-history", headers=headers).get_json()["data"]["items"]
    actions = [h["action"] for h in history]
    assert "collection.started" in actions
    assert "collection.completed" in actions


def test_collect_enabled_sources_bulk(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _create_source(client, headers, project_id, url="https://a.example.test/list")
    _create_source(client, headers, project_id, url="https://b.example.test/list")
    _mock_public_dns(monkeypatch, {"a.example.test", "b.example.test"})

    def responder(url):
        if url.endswith("/robots.txt"):
            return _no_robots(url)
        return _FakeResponse(html=PUBLIC_HTML)
    _mock_get(monkeypatch, responder)

    resp = client.post(f"/api/v1/projects/{project_id}/sources/collect-enabled", headers=headers)
    assert resp.status_code == 200
    items = resp.get_json()["data"]["items"]
    assert len(items) == 2
    assert all(i["status"] == "completed" for i in items)


# ---------------------------------------------------------------- SSRF / SECURITY

def test_ssrf_loopback_ip_blocked_directly():
    from app.errors.exceptions import CollectionError
    from app.services.collectors.security import validate_url_ssrf

    with pytest.raises(CollectionError) as exc:
        validate_url_ssrf("http://127.0.0.1/admin")
    assert exc.value.code == "COLLECTION_SSRF_BLOCKED"


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",  # link-local (cloud metadata endpoint)
    "http://10.0.0.5/",
    "http://172.16.0.5/",
    "http://192.168.0.5/",
    "http://[::1]/",           # IPv6 loopback
    "http://[fc00::1]/",       # IPv6 unique local (private) address
    "http://[fe80::1]/",       # IPv6 link-local address
])
def test_ssrf_private_ranges_blocked_directly(url):
    from app.errors.exceptions import CollectionError
    from app.services.collectors.security import validate_url_ssrf

    with pytest.raises(CollectionError) as exc:
        validate_url_ssrf(url)
    assert exc.value.code == "COLLECTION_SSRF_BLOCKED"


def test_ssrf_connect_hook_blocks_real_socket_connect():
    """Exercises the real urllib3 connect path (ssrf_safe_connections), not
    the mocked requests.Session.get used by every other test in this file —
    this is what actually closes the DNS-rebinding TOCTOU gap: the hook
    re-validates the literal address at connect time, inside urllib3's own
    connect function, not just via an earlier separate check.
    """
    from app.errors.exceptions import CollectionError
    from app.services.collectors.security import ssrf_safe_connections
    import requests

    with pytest.raises(CollectionError) as exc:
        with ssrf_safe_connections():
            requests.get("http://192.168.222.111/", timeout=2)
    assert exc.value.code == "COLLECTION_SSRF_BLOCKED"


def test_ssrf_redirect_to_private_ip_blocked(client, monkeypatch):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    _mock_public_dns(monkeypatch, {"reviews.example.test"})

    def fake_get(self, url, **kwargs):
        if "reviews.example.test" in url:
            return _FakeResponse(status_code=302, headers={"Location": "http://192.168.1.5/internal"})
        return _FakeResponse(html=PUBLIC_HTML)
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(requests, "get", lambda url, **kw: _no_robots(url))

    resp = client.post(f"/api/v1/sources/{source_id}/test-connection", headers=headers)
    assert resp.get_json()["data"]["available"] is False  # SSRF-blocked redirect surfaces as unavailable, never followed


def test_path_traversal_scheme_rejected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"type": "review_site", "url": "javascript:alert(1)"}, headers=headers,
    )
    assert resp.status_code == 400


def test_cross_organisation_uuid_denied_on_preview(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)

    _, other_headers = owner_context(client, org_name="Other Org6b", email="other6b@other.test")
    resp = client.post(f"/api/v1/sources/{source_id}/preview", headers=other_headers)
    assert resp.status_code == 404


def test_missing_permission_denied(client):
    """Viewer role only has view_reviews — collect (manage_data_sources) must be denied."""
    from tests.conftest_project import owner_context as _owner
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)

    # Register a second user, add them to the same org with the built-in Viewer role.
    from app.extensions import db
    from app.models import Role, MemberRole, OrganisationMember, User
    reg = client.post("/api/v1/auth/register", json={
        "organisationName": "Viewer Co", "email": "viewerperm@acme.test",
        "password": "Str0ngPassw0rd!", "name": "Vera Viewer",
    }).get_json()["data"]
    login = client.post("/api/v1/auth/login", json={"email": "viewerperm@acme.test", "password": "Str0ngPassw0rd!"}).get_json()["data"]

    with client.application.app_context():
        member = OrganisationMember(organisation_id=org_id, user_id=reg["userId"], status=OrganisationMember.STATUS_ACTIVE)
        db.session.add(member)
        db.session.flush()
        viewer_role = Role.query.filter_by(organisation_id=None, name="Viewer").first()
        db.session.add(MemberRole(organisation_member_id=member.id, role_id=viewer_role.id))
        db.session.commit()

    viewer_headers = {"Authorization": f"Bearer {login['accessToken']}", "X-Organisation-Id": org_id}
    resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=viewer_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------- CONCURRENCY (final-QA hardening)

def test_concurrent_collection_returns_busy_not_a_race(client, monkeypatch, app):
    """A second collection call that can't acquire the process-wide lock
    within the timeout gets a clear COLLECTION_BUSY error, never a hang and
    never silent SSRF-hook interference from a concurrently-running call.
    """
    import app.services.collection_service as collection_service_module

    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)

    monkeypatch.setattr(collection_service_module, "_LOCK_ACQUIRE_TIMEOUT_SECONDS", 0.2)

    with app.app_context():
        acquired = collection_service_module._collection_lock.acquire(timeout=1)
        assert acquired
        try:
            resp = client.post(f"/api/v1/sources/{source_id}/test-connection", headers=headers)
            assert resp.status_code == 503
            assert resp.get_json()["error"]["code"] == "COLLECTION_BUSY"
        finally:
            collection_service_module._collection_lock.release()

    # lock is free again — a normal call succeeds without hanging
    resp2 = client.post(f"/api/v1/sources/{source_id}/test-connection", headers=headers)
    assert resp2.status_code == 200


def test_collection_lock_released_after_exception(client, app):
    """The lock must release even when the locked call raises (e.g. a
    disabled source) — otherwise one failed request would permanently wedge
    every future collection call in this process.
    """
    import app.services.collection_service as collection_service_module

    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    source_id = _create_source(client, headers, project_id)
    client.patch(f"/api/v1/sources/{source_id}", json={"enabled": False}, headers=headers)

    resp = client.post(f"/api/v1/sources/{source_id}/collect", headers=headers)
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "COLLECTION_SOURCE_DISABLED"

    with app.app_context():
        # If the lock were still held, this would block until test timeout.
        acquired = collection_service_module._collection_lock.acquire(timeout=2)
        assert acquired, "lock was not released after an exception in the locked section"
        collection_service_module._collection_lock.release()
