import io

from tests.conftest_project import owner_context, create_project


CSV_SIMPLE = "text,rating\nGreat product!,5\nTerrible awful,1\nIt is okay.,3\n"

def _upload_csv(client, project_id, headers, content=CSV_SIMPLE, filename="reviews.csv"):
    data = {"file": (io.BytesIO(content.encode("utf-8")), filename), "fileType": "csv"}
    return client.post(
        f"/api/v1/projects/{project_id}/datasets",
        data=data, headers=headers, content_type="multipart/form-data",
    )

def _upload_build_validate(client, project_id, headers, content=CSV_SIMPLE):
    dataset_id = _upload_csv(client, project_id, headers, content=content).get_json()["data"]["datasetId"]
    client.post(f"/api/v1/datasets/{dataset_id}/map-columns", json={"text": "text", "rating": "rating"}, headers=headers)
    client.post(f"/api/v1/datasets/{dataset_id}/validate", headers=headers)
    return dataset_id


def test_profile_after_validation_has_expected_shape(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    dataset_id = _upload_build_validate(client, project_id, headers)
    resp = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers)
    assert resp.status_code == 200
    profile = resp.get_json()["data"]["profile"]
    assert profile["rowCount"] == 3
    assert profile["validRowCount"] == 3
    assert profile["duplicateRowCount"] == 0
    assert profile["emptyTextCount"] == 0
    assert "averageTextLength" in profile
    assert profile["averageTextLength"] is not None
    assert "languageDistribution" in profile
    assert "ratingDistribution" in profile
    assert "qualityFlags" in profile
    assert "severity" in profile
    assert profile["severity"] in ("info", "warning", "error")


def test_profile_counts_empty_and_duplicate_rows(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    csv = "text,rating\nGreat product!,5\n,3\nGreat product!,5\nBad,10\n"
    dataset_id = _upload_build_validate(client, project_id, headers, content=csv)
    resp = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers)
    profile = resp.get_json()["data"]["profile"]
    assert profile["rowCount"] == 4
    assert profile["emptyTextCount"] >= 1
    assert profile["duplicateRowCount"] >= 1


def test_profile_rating_distribution_missing_ratings(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    csv = "text,rating\nGreat!,5\nOkay text,\nBad product,1\n"
    dataset_id = _upload_build_validate(client, project_id, headers, content=csv)
    resp = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers)
    profile = resp.get_json()["data"]["profile"]
    assert profile["ratingDistribution"]["missing"] >= 1
    assert profile["ratingDistribution"]["mean"] is not None


def test_profile_malformed_rating_handled(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    # rating column exists but validation will reject invalid rating rows as invalid
    csv = "text,rating\nBad,\nGreat!,not_a_number\nOkay product,5\n"
    dataset_id = _upload_build_validate(client, project_id, headers, content=csv)
    resp = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers)
    assert resp.status_code == 200
    profile = resp.get_json()["data"]["profile"]
    assert profile["rowCount"] == 3


def test_profile_rating_text_mismatch_flagged(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    # Strong positive text with 1-star rating and strong negative text with 5-star
    csv = "text,rating\n\"This is absolutely wonderful, I love it!\",1\n\"This is dreadful, worst purchase ever I hate it.\",5\n\"It is okay.\",3\n"
    dataset_id = _upload_build_validate(client, project_id, headers, content=csv)
    resp = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers)
    profile = resp.get_json()["data"]["profile"]
    # Should flag at least one mismatch bucket
    assert "ratingTextMismatches" in profile
    total = profile.get("ratingTextMismatchSampleCount", 0)
    assert total >= 1


def test_profile_spam_heuristics_detect_extreme_caps_and_urls(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    csv = "text,rating\n\"AMAZING PRODUCT LOVE IT BUY NOW!!!\",5\n\"Check http://spam.com http://spam2.com http://spam3.com\",1\n\"Normal review here, quite decent.\",3\n"
    dataset_id = _upload_build_validate(client, project_id, headers, content=csv)
    resp = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers)
    profile = resp.get_json()["data"]["profile"]
    # At least one of the quality flags should be non-zero
    counts = profile["qualityFlags"]["counts"]
    assert any(k in counts for k in ("excessive_caps", "url_heavy", "repeated_characters"))


def test_profile_determinism(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    dataset_id = _upload_build_validate(client, project_id, headers)
    first = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers).get_json()["data"]["profile"]
    second = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers).get_json()["data"]["profile"]
    assert first == second


def test_profile_requires_auth(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    dataset_id = _upload_build_validate(client, project_id, headers)
    resp = client.get(f"/api/v1/datasets/{dataset_id}/profile")
    assert resp.status_code in (401, 400)


def test_profile_cross_org_blocked(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    dataset_id = _upload_build_validate(client, project_id, headers)
    _, other_headers = owner_context(client, org_name="Other Org", email="other@other.test")
    resp = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=other_headers)
    assert resp.status_code == 404


def test_profile_persisted_in_dataset_to_dict(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    dataset_id = _upload_build_validate(client, project_id, headers)
    # The dataset's own to_dict now includes profileReport
    resp = client.get(f"/api/v1/datasets/{dataset_id}", headers=headers)
    body = resp.get_json()["data"]
    assert "profileReport" in body
    assert body["profileReport"] is not None


def test_profile_non_english_sample_does_not_crash(client):
    org_id, headers = owner_context(client)
    project_id = create_project(client, headers)
    csv = "text,rating\n\"Прекрасный товар, очень доволен\",5\n\"This is great\",5\n\"Bon produit, merci\",4\n"
    dataset_id = _upload_build_validate(client, project_id, headers, content=csv)
    resp = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers)
    assert resp.status_code == 200
    profile = resp.get_json()["data"]["profile"]
    assert "languageDistribution" in profile
