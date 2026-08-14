import io

from app.models import Review
from tests.conftest_project import owner_context, create_project

CSV_CONTENT = (
    "text,rating,date,source\n"
    "Great product!,5,2026-01-01,siteA\n"
    ",3,2026-01-02,siteA\n"
    "Great product!,5,2026-01-01,siteA\n"
    "Bad,10,2026-01-03,siteA\n"
)

CRITIC_SHAPED_CSV = (
    "grade,publication,text,date\n"
    "100,Forbes,An excellent and thoughtful review.,2020-03-16\n"
    "95,IGN,Strong writing and memorable characters.,2020-03-17\n"
)


def _upload_csv(client, project_id, headers, content=CSV_CONTENT, filename="reviews.csv"):
    data = {
        "file": (io.BytesIO(content.encode("utf-8")), filename),
        "fileType": "csv",
    }
    return client.post(
        f"/api/v1/projects/{project_id}/datasets",
        data=data,
        headers=headers,
        content_type="multipart/form-data",
    )


def test_upload_dataset(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    resp = _upload_csv(client, project_id, headers)
    assert resp.status_code == 202
    assert resp.get_json()["data"]["status"] == "uploaded"


def test_get_dataset_returns_preview(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    dataset_id = _upload_csv(client, project_id, headers).get_json()["data"]["datasetId"]

    resp = client.get(f"/api/v1/datasets/{dataset_id}", headers=headers)
    assert resp.status_code == 200
    preview = resp.get_json()["data"]["preview"]
    assert "text" in preview["columns"]
    assert preview["totalRows"] == 4


def test_map_columns_rejects_unknown_column(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    dataset_id = _upload_csv(client, project_id, headers).get_json()["data"]["datasetId"]

    resp = client.post(
        f"/api/v1/datasets/{dataset_id}/map-columns",
        json={"text": "nonexistent_column"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_full_pipeline_validate_and_process(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    dataset_id = _upload_csv(client, project_id, headers).get_json()["data"]["datasetId"]

    map_resp = client.post(
        f"/api/v1/datasets/{dataset_id}/map-columns",
        json={"text": "text", "rating": "rating", "date": "date", "source": "source"},
        headers=headers,
    )
    assert map_resp.status_code == 200

    validate_resp = client.post(f"/api/v1/datasets/{dataset_id}/validate", headers=headers)
    assert validate_resp.status_code == 202
    body = validate_resp.get_json()["data"]
    assert body["rowCount"] == 4
    assert body["validRowCount"] == 2
    assert body["invalidRowCount"] == 2
    assert body["duplicateRowCount"] == 1
    assert body["status"] == "validated"

    process_resp = client.post(f"/api/v1/datasets/{dataset_id}/process", headers=headers)
    assert process_resp.status_code == 202
    assert process_resp.get_json()["data"]["status"] == "processed"

    reviews_resp = client.get(f"/api/v1/projects/{project_id}/reviews", headers=headers)
    reviews = reviews_resp.get_json()["data"]["items"]
    assert len(reviews) == 2
    assert sum(1 for r in reviews if r["isDuplicate"]) == 1
    assert all(r["datasetId"] == dataset_id for r in reviews)


def test_process_without_validate_rejected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    dataset_id = _upload_csv(client, project_id, headers).get_json()["data"]["datasetId"]
    client.post(
        f"/api/v1/datasets/{dataset_id}/map-columns", json={"text": "text"}, headers=headers,
    )
    resp = client.post(f"/api/v1/datasets/{dataset_id}/process", headers=headers)
    assert resp.status_code == 400


def test_dataset_cross_org_access_denied(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    dataset_id = _upload_csv(client, project_id, headers).get_json()["data"]["datasetId"]

    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.get(f"/api/v1/datasets/{dataset_id}", headers=other_headers)
    assert resp.status_code == 404


def test_delete_dataset(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    dataset_id = _upload_csv(client, project_id, headers).get_json()["data"]["datasetId"]

    del_resp = client.delete(f"/api/v1/datasets/{dataset_id}", headers=headers)
    assert del_resp.status_code == 200

    list_resp = client.get(f"/api/v1/projects/{project_id}/datasets", headers=headers)
    assert list_resp.get_json()["data"]["items"] == []


def test_critic_shape_reports_actionable_rating_validation_without_reviews(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers, name="Animal Crossing reviews")
    dataset_id = _upload_csv(client, project_id, headers, CRITIC_SHAPED_CSV, "critic.csv").get_json()["data"]["datasetId"]
    mapped = client.post(f"/api/v1/datasets/{dataset_id}/map-columns", json={"text": "text", "rating": "grade", "date": "date", "source": "publication"}, headers=headers)
    assert mapped.status_code == 200
    validation = client.post(f"/api/v1/datasets/{dataset_id}/validate", headers=headers)
    assert validation.status_code == 400
    error = validation.get_json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "rating must be between 0 and 5" in error["details"]["errors"][0]["reason"]
    assert error["details"]["stage"] == "validation"
    assert Review.query.filter_by(project_id=project_id).count() == 0

    # Correcting the mapping by leaving the incompatible critic score
    # unmapped allows the text/date/publication fields to process normally.
    client.post(f"/api/v1/datasets/{dataset_id}/map-columns", json={"text": "text", "date": "date", "source": "publication"}, headers=headers)
    corrected = client.post(f"/api/v1/datasets/{dataset_id}/validate", headers=headers)
    assert corrected.status_code == 202
    assert client.post(f"/api/v1/datasets/{dataset_id}/process", headers=headers).status_code == 202
    reviews = Review.query.filter_by(project_id=project_id).all()
    assert len(reviews) == 2
    assert {review.source for review in reviews} == {"Forbes", "IGN"}
    assert {review.review_date.isoformat() for review in reviews} == {"2020-03-16", "2020-03-17"}


def test_identical_file_same_project_is_rejected(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    first = _upload_csv(client, project_id, headers, filename="same.csv")
    assert first.status_code == 202
    second = _upload_csv(client, project_id, headers, filename="renamed.csv")
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "DATASET_ALREADY_UPLOADED"


def test_failed_identical_file_can_retry_without_new_dataset(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    first = _upload_csv(client, project_id, headers, CRITIC_SHAPED_CSV, "critic.csv")
    dataset_id = first.get_json()["data"]["datasetId"]
    client.post(f"/api/v1/datasets/{dataset_id}/map-columns", json={"text": "text", "rating": "grade"}, headers=headers)
    assert client.post(f"/api/v1/datasets/{dataset_id}/validate", headers=headers).status_code == 400
    retry = _upload_csv(client, project_id, headers, CRITIC_SHAPED_CSV, "critic.csv")
    assert retry.status_code == 202
    assert retry.get_json()["data"]["datasetId"] == dataset_id
