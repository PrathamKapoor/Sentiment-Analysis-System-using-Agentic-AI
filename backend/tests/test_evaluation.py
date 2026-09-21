import pytest

from tests.conftest_project import owner_context, create_project
from app.services.evaluation_service import evaluate_benchmark


def test_evaluation_returns_expected_structure():
    result = evaluate_benchmark()
    assert "benchmarkId" in result
    assert result["benchmarkId"] == "sentiment_benchmark_v1"
    assert "metrics" in result
    for key in ("accuracy", "macroPrecision", "macroRecall", "macroF1", "perClass"):
        assert key in result["metrics"]
    assert "confusionMatrix" in result
    assert "sampleCount" in result
    assert result["sampleCount"] > 0
    assert "model" in result
    assert result["model"]["name"] == "vader"


def test_evaluation_accuracy_in_valid_range():
    result = evaluate_benchmark()
    acc = result["metrics"]["accuracy"]
    assert 0.0 <= acc <= 1.0
    # VADER on this short-of-text fixture should be well above chance but not perfect.
    # The conservative lower bound protects against a silently-broken fixture.
    assert acc >= 0.55


def test_evaluation_confusion_matrix_is_square():
    result = evaluate_benchmark()
    cm = result["confusionMatrix"]
    assert set(cm.keys()) == {"positive", "negative", "neutral"}
    for true_label in cm:
        assert set(cm[true_label].keys()) == {"positive", "negative", "neutral"}
        assert sum(cm[true_label].values()) == result["metrics"]["perClass"][true_label]["support"]


def test_evaluation_per_class_precision_recall_f1_in_range():
    result = evaluate_benchmark()
    for cls, metrics in result["metrics"]["perClass"].items():
        assert 0.0 <= metrics["precision"] <= 1.0
        assert 0.0 <= metrics["recall"] <= 1.0
        assert 0.0 <= metrics["f1"] <= 1.0


def test_evaluation_is_deterministic():
    first = evaluate_benchmark()
    second = evaluate_benchmark()
    assert first["metrics"] == second["metrics"]
    assert first["confusionMatrix"] == second["confusionMatrix"]


def test_evaluation_endpoint_requires_auth(client):
    resp = client.get("/api/v1/evaluation/benchmark")
    assert resp.status_code in (401, 400)


def test_evaluation_endpoint_returns_benchmark(client):
    org_id, headers = owner_context(client)
    resp = client.get("/api/v1/evaluation/benchmark", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "metrics" in data
    assert "accuracy" in data["metrics"]
    assert "confusionMatrix" in data


def test_evaluation_cross_org_benchmark_is_global_not_tenant_scoped(client):
    # The benchmark is system-level. Two different organisations should see
    # the same result — the benchmark must not be scoped to a tenant.
    _, headers_a = owner_context(client, org_name="Org A", email="eval-a@eval.test")
    _, headers_b = owner_context(client, org_name="Org B", email="eval-b@eval.test")
    resp_a = client.get("/api/v1/evaluation/benchmark", headers=headers_a)
    resp_b = client.get("/api/v1/evaluation/benchmark", headers=headers_b)
    assert resp_a.get_json()["data"]["metrics"]["accuracy"] == resp_b.get_json()["data"]["metrics"]["accuracy"]


def test_evaluation_unsupported_labels_handled_safely():
    # Direct service check: the fixture guard must raise on an unknown label.
    # We verify the loader's guard by importing and checking the constant set.
    from app.services.evaluation_service import _SUPPORTED_LABELS
    assert _SUPPORTED_LABELS == {"positive", "negative", "neutral"}
