from datetime import datetime, timezone

from app.extensions import db
from app.utils.uuid_type import GUID, new_uuid


def utcnow():
    return datetime.now(timezone.utc)


class UUIDPrimaryKeyMixin:
    id = db.Column(GUID(), primary_key=True, default=new_uuid)


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class SoftDeleteMixin:
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True, default=None)

    @property
    def is_deleted(self):
        return self.deleted_at is not None
