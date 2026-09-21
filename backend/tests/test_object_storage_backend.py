"""Tests for the S3StorageBackend interface using a mocked boto3.

These tests do NOT require a real S3 bucket. They verify that the
backend:

  * constructs correctly from configuration
  * raises a clear error when boto3 is not installed
  * raises a clear error when S3_BUCKET is missing
  * defers boto3 import to first use (so constructing the backend
    does not require network access)
  * rejects path-traversal keys
  * round-trips a payload when boto3 is faked in via sys.modules

The unit tests with a fake boto3 are what would validate a real
implementation against AWS/MinIO/R2 without leaving the workstation.
"""
from __future__ import annotations

import os
import sys
import types
from unittest import mock

import pytest

from app.services import storage_service
from app.services.storage_service import S3StorageBackend


@pytest.fixture
def fake_boto3_module(monkeypatch):
    """Install a fake boto3 in sys.modules that records calls and
    round-trips a small in-memory bucket dict."""
    fake = types.ModuleType("boto3")

    class _FakeBody:
        def __init__(self, data):
            self._data = data

        def read(self):
            return self._data

    class _FakeClient:
        def __init__(self):
            self.bucket = {}
            self.calls = []

        def put_object(self, **kwargs):
            self.calls.append(("put_object", kwargs))
            self.bucket[kwargs["Key"]] = kwargs["Body"]
            return {"ETag": "deadbeef"}

        def get_object(self, **kwargs):
            return {"Body": _FakeBody(self.bucket[kwargs["Key"]])}

        def delete_object(self, **kwargs):
            self.calls.append(("delete_object", kwargs))
            self.bucket.pop(kwargs["Key"], None)
            return {}

    fake_client = _FakeClient()
    fake.client = lambda *a, **kw: fake_client
    fake._fake_client = fake_client
    monkeypatch.setitem(sys.modules, "boto3", fake)
    yield fake


def test_s3_backend_missing_boto3_raises(monkeypatch):
    """Without boto3 installed, save_bytes must fail with a clear
    error rather than silently falling back to local disk."""
    # Remove any cached boto3 module so the import inside save_bytes
    # actually fails.
    monkeypatch.delitem(sys.modules, "boto3", raising=False)

    b = S3StorageBackend(bucket="b", region="us-east-1")
    with pytest.raises(RuntimeError, match="boto3"):
        b.save_bytes(b"hello", name="x.txt")


def test_s3_backend_missing_bucket_env(monkeypatch):
    """STORAGE_BACKEND=s3 without S3_BUCKET must refuse to start."""
    storage_service.reset_storage(None)
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.setitem(sys.modules, "boto3", types.ModuleType("boto3"))
    try:
        from app import create_app

        app = create_app("testing")
        with app.app_context():
            with pytest.raises(RuntimeError, match="S3_BUCKET"):
                storage_service.get_storage()
    finally:
        monkeypatch.delitem(sys.modules, "boto3", raising=False)
        storage_service.reset_storage(None)


def test_s3_backend_rejects_path_traversal():
    b = S3StorageBackend(bucket="b", region="us-east-1")
    with pytest.raises(ValueError, match="unsafe storage key"):
        b._full_key("../etc/passwd")
    with pytest.raises(ValueError, match="unsafe storage key"):
        b._full_key("/absolute")


def test_s3_backend_round_trip(fake_boto3_module):
    fake_client = fake_boto3_module._fake_client
    b = S3StorageBackend(
        bucket="phase13-bucket",
        region="us-east-1",
        key_prefix="reports",
    )

    key = b.save_bytes(
        b"hello-pdf-bytes", name="abc.pdf", content_type="application/pdf"
    )
    assert key == "abc.pdf"
    put = next(c for c in fake_client.calls if c[0] == "put_object")
    assert put[1]["Bucket"] == "phase13-bucket"
    assert put[1]["Key"] == "reports/abc.pdf"
    assert put[1]["Body"] == b"hello-pdf-bytes"
    assert put[1]["ContentType"] == "application/pdf"

    body = b.open_read("abc.pdf")
    assert body == b"hello-pdf-bytes"

    desc = b.describe()
    assert desc["backend"] == "s3"
    assert desc["bucket"] == "phase13-bucket"
    assert desc["key_prefix"] == "reports"

    b.delete("abc.pdf")
    assert "reports/abc.pdf" not in fake_client.bucket


def test_default_storage_backend_is_local(monkeypatch):
    """Without STORAGE_BACKEND=s3, get_storage returns a local backend
    in a Flask app context. This pins the documented default."""
    storage_service.reset_storage(None)
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    from app import create_app

    app = create_app("testing")
    with app.app_context():
        s = storage_service.get_storage()
        assert s.describe()["backend"] in ("local", "ephemeral")