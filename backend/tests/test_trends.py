from datetime import date

from tests.conftest_project import owner_context, create_project, create_reviews_directly


def _seed_and_analyse(client, project_id, headers):
    create_reviews_directly(project_id, ["Great product!"], review_date=date(2026, 1, 1))
    create_reviews_directly(project_id, ["Great product again!"], review_date=date(2026, 1, 2))
    create_reviews_directly(project_id, ["Terrible experience."], review_date=date(2026, 2, 15))
    client.post(f"/api/v1/projects/{project_id}/analysis/sentiment", json={}, headers=headers)


def test_daily_aggregation(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/trends", query_string={"granularity": "daily"}, headers=headers
    )
    body = resp.get_json()["data"]
    assert body["granularity"] == "daily"
    periods = {p["period"]: p for p in body["periods"]}
    assert periods["2026-01-01"]["totalReviews"] == 1
    assert periods["2026-01-02"]["totalReviews"] == 1
    assert periods["2026-02-15"]["totalReviews"] == 1


def test_weekly_aggregation(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/trends", query_string={"granularity": "weekly"}, headers=headers
    )
    periods = resp.get_json()["data"]["periods"]
    # Jan 1 and Jan 2, 2026 fall in the same ISO week (Mon Dec 29 2025 - Sun Jan 4 2026).
    jan_week = next(p for p in periods if p["period"] == "2025-12-29")
    assert jan_week["totalReviews"] == 2


def test_monthly_aggregation(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/trends", query_string={"granularity": "monthly"}, headers=headers
    )
    periods = {p["period"]: p for p in resp.get_json()["data"]["periods"]}
    assert periods["2026-01"]["totalReviews"] == 2
    assert periods["2026-02"]["totalReviews"] == 1


def test_date_filter(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/trends",
        query_string={"granularity": "daily", "dateFrom": "2026-02-01"},
        headers=headers,
    )
    periods = resp.get_json()["data"]["periods"]
    assert len(periods) == 1
    assert periods[0]["period"] == "2026-02-15"


def test_source_filter(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    from app.models import DataSource
    real_source_id = str(DataSource.query.first().id)

    resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/trends",
        query_string={"sourceId": real_source_id},
        headers=headers,
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]["periods"]) >= 1


def test_dataset_filter_returns_empty_when_no_match(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    import uuid
    resp = client.get(
        f"/api/v1/projects/{project_id}/analysis/trends",
        query_string={"datasetId": str(uuid.uuid4())},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["periods"] == []


def test_percentages_valid(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    _seed_and_analyse(client, project_id, headers)

    resp = client.get(f"/api/v1/projects/{project_id}/analysis/trends", headers=headers)
    for period in resp.get_json()["data"]["periods"]:
        total_pct = period["positivePercentage"] + period["negativePercentage"] + period["neutralPercentage"]
        assert 99.0 <= total_pct <= 101.0  # rounding tolerance


def test_empty_result_handled(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)

    resp = client.get(f"/api/v1/projects/{project_id}/analysis/trends", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["periods"] == []
