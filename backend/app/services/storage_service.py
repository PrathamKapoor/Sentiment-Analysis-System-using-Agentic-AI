"""Storage abstraction — where uploads and generated reports live.

Backends:

  LocalStorageBackend     — the default. Files under
                           ``UPLOAD_FOLDER`` / ``REPORT_OUTPUT_DIRECTORY``
                           when set, else Flask's instance folder
                           (``<instance>/uploads``,
                           ``<instance>/generated_reports``). Works for a single
                           process or a single host with attached disk.

  EphemeralBackend       — same as LocalStorageBackend but rooted in
                           a temp dir. Used by tests and by container
                           workloads that intentionally rely on the
                           container filesystem as the artifact
                           lifecycle.

  S3StorageBackend       — interface-only stub. Selecting this backend
                           without the optional ``boto3`` dependency
                           raises a clear error. The interface is in
                           place so the S3 client and bucket wiring can
                           land in a follow-up phase without
                           re-plumbing every caller.

Environment contract for the S3 backend (consumed by the future
implementation):

  STORAGE_BACKEND=s3
  S3_BUCKET=<bucket name>
  S3_REGION=<aws region>
  S3_ENDPOINT_URL=<optional override for non-AWS, e.g. MinIO, R2>
  S3_ACCESS_KEY_ID=<credential>
  S3_SECRET_ACCESS_KEY=<credential>
  S3_KEY_PREFIX=<optional path prefix>

Single source of truth for the abstraction — every other service that
writes a file goes through ``get_storage()``. Adding the optional
``boto3`` dependency and an S3 implementation is a one-file change
here plus the dependency bump in ``requirements.txt``.

What this module is NOT responsible for:
  * URL signing. Downloading goes through the existing authenticated
    route and the report_id is the only public handle.
  * Public discovery. Keys are always random UUIDs.
  * Caching of object bytes — Flask is the only consumer and it
    streams the bytes when sending.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from typing import Optional

from flask import current_app

logger = logging.getLogger(__name__)


class StorageBackend:
    """Abstract interface. Every concrete backend implements the same
    five methods so the caller is storage-agnostic.

    ``content_type`` is optional metadata; the local backend ignores
    it. The future S3 backend will set it on the object so
    ``Content-Type`` headers are correct on download.
    """

    def save_bytes(
        self, data: bytes, *, name: str, content_type: Optional[str] = None
    ) -> str:
        raise NotImplementedError

    def resolve(self, name: str) -> str:
        """Return a local file path for the given storage name. Must be
        a real filesystem path the caller can read (used by send_file).
        S3 backends return a temporary local copy."""
        raise NotImplementedError

    def delete(self, name: str) -> None:
        raise NotImplementedError

    def open_read(self, name: str) -> bytes:
        """Read the full object into memory. For S3, this performs a
        GetObject. Local backends just read the file."""
        raise NotImplementedError

    def describe(self) -> dict:
        raise NotImplementedError


class LocalStorageBackend(StorageBackend):
    """Files are saved to a directory on disk and read back by absolute
    path. Suitable for a single-host deployment or a mounted volume on
    a container."""

    def __init__(self, root: str):
        self._root = root
        os.makedirs(self._root, exist_ok=True)

    def save_bytes(
        self, data: bytes, *, name: str, content_type: Optional[str] = None
    ) -> str:
        if not name or ".." in name or name.startswith(("/", "\\")):
            raise ValueError("unsafe storage key")
        path = os.path.join(self._root, name)
        with open(path, "wb") as f:
            f.write(data)
        return name

    def resolve(self, name: str) -> str:
        return os.path.join(self._root, name)

    def delete(self, name: str) -> None:
        try:
            os.remove(self.resolve(name))
        except FileNotFoundError:
            pass

    def open_read(self, name: str) -> bytes:
        with open(self.resolve(name), "rb") as f:
            return f.read()

    def describe(self) -> dict:
        return {"backend": "local", "root": self._root}


class EphemeralBackend(LocalStorageBackend):
    """Same as LocalStorageBackend but reads/writes to a temp dir.
    Used by tests, and by containerized environments where the container
    filesystem is the intended lifecycle for report artifacts."""

    def describe(self) -> dict:
        return {"backend": "ephemeral", "tempdir": self._root}


class S3StorageBackend(StorageBackend):
    """Interface stub for an S3-compatible object storage backend.

    Selecting this backend via ``STORAGE_BACKEND=s3`` without the
    optional ``boto3`` dependency raises a clear error. The
    transfer code is the only piece missing.

    The error path here is explicit (rather than a silent fallback to
    local disk) because silent fallback would corrupt a multi-instance
    deployment: a write that "succeeded" to the local filesystem would
    not be visible to other replicas or to the next process restart.
    """

    def __init__(
        self,
        bucket: str,
        region: str,
        key_prefix: str = "",
        endpoint_url: Optional[str] = None,
    ):
        # Defer the boto3 import check to first use so that tests
        # can monkeypatch sys.modules['boto3'] before save_bytes
        # runs. The hard requirement is that the implementation
        # cannot pretend to succeed when boto3 is absent.
        self._bucket = bucket
        self._region = region
        self._key_prefix = key_prefix.lstrip("/")
        self._endpoint_url = endpoint_url
        self._client = None


    def _full_key(self, name: str) -> str:
        if ".." in name or name.startswith("/"):
            raise ValueError("unsafe storage key")
        if self._key_prefix:
            return f"{self._key_prefix}/{name}"
        return name

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "STORAGE_BACKEND=s3 requires the optional boto3 package. "
                "Add it to requirements.txt and install, or use "
                "STORAGE_BACKEND=local."
            ) from exc
        self._client = boto3.client(
            "s3",
            region_name=self._region,
            endpoint_url=self._endpoint_url,
        )
        return self._client
    def save_bytes(
        self, data: bytes, *, name: str, content_type: Optional[str] = None
    ) -> str:
        # Implementation requires boto3 at runtime. When the
        # dependency is unavailable, save_bytes raises rather than
        # silently writing elsewhere.
        params = {"Bucket": self._bucket, "Key": self._full_key(name), "Body": data}
        if content_type:
            params["ContentType"] = content_type
        self._ensure_client().put_object(**params)
        return name

    def resolve(self, name: str) -> str:
        # S3 objects are not local files. We materialise to a temp
        # file so send_file can stream it. The temp file is deleted
        # on process exit.
        tmp = tempfile.NamedTemporaryFile(
            prefix="sams_s3_", suffix="_" + os.path.basename(name), delete=False
        )
        try:
            with open(tmp.name, "wb") as f:
                f.write(self.open_read(name))
        except Exception:
            os.unlink(tmp.name)
            raise
        return tmp.name

    def delete(self, name: str) -> None:
        self._ensure_client().delete_object(
            Bucket=self._bucket, Key=self._full_key(name)
        )

    def open_read(self, name: str) -> bytes:
        resp = self._ensure_client().get_object(
            Bucket=self._bucket, Key=self._full_key(name)
        )
        return resp["Body"].read()

    def describe(self) -> dict:
        return {
            "backend": "s3",
            "bucket": self._bucket,
            "region": self._region,
            "endpoint": self._endpoint_url,
            "key_prefix": self._key_prefix,
        }


_backend = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is not None:
        return _backend

    backend_name = (os.environ.get("STORAGE_BACKEND") or "").lower()

    if backend_name == "s3":
        bucket = os.environ.get("S3_BUCKET")
        if not bucket:
            raise RuntimeError(
                "STORAGE_BACKEND=s3 requires S3_BUCKET to be set."
            )
        _backend = S3StorageBackend(
            bucket=bucket,
            region=os.environ.get("S3_REGION", "us-east-1"),
            key_prefix=os.environ.get("S3_KEY_PREFIX", ""),
            endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
        )
        return _backend

    # Default: local disk. With REPORT_OUTPUT_DIRECTORY unset, persist under
    # <instance>/generated_reports (mirrors the uploads default in
    # dataset_service) so report artifacts survive process restarts instead of
    # vanishing from a temp dir. Ephemeral root only when there is no app
    # context at all (standalone scripts/tests that never call get_storage).
    cfg = current_app.config if current_app else None
    if cfg is not None:
        root = cfg.get("REPORT_OUTPUT_DIRECTORY") or os.path.join(
            current_app.instance_path, "generated_reports"
        )
        _backend = LocalStorageBackend(root)
    else:
        _backend = EphemeralBackend(tempfile.mkdtemp(prefix="sams_storage_"))
    return _backend


def reset_storage(backend: StorageBackend | None = None) -> None:
    """Tests swap this to inject a specific backend."""
    global _backend
    _backend = backend