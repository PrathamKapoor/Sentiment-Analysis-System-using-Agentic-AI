import json
import os
import uuid
from datetime import date, datetime

from flask import current_app

from app.extensions import db
from app.errors.exceptions import ValidationError
from app.models import Dataset, Review
from app.services.dataset_file_parser import read_columns_and_rows
from app.services.text_cleaning import clean_text, normalize_for_dedup

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_FILE_TYPES = {
    "csv": {"text/csv", "application/vnd.ms-excel", "application/octet-stream"},
    "json": {"application/json", "text/json", "application/octet-stream"},
    "excel": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/octet-stream",
    },
}
MAPPABLE_FIELDS = ("text", "rating", "date", "source")
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d")

PREVIEW_ROW_LIMIT = 20
MAX_ERROR_SAMPLES = 20


def _upload_dir():
    upload_dir = current_app.config.get("UPLOAD_FOLDER") or os.path.join(
        current_app.instance_path, "uploads"
    )
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def list_datasets(project_id):
    return Dataset.query.filter_by(project_id=project_id).filter(
        Dataset.deleted_at.is_(None)
    ).order_by(Dataset.created_at.desc()).all()


def create_dataset(project_id, uploaded_by, file_storage, file_type):
    if file_type not in Dataset.FILE_TYPES:
        raise ValidationError(f"fileType must be one of: {', '.join(Dataset.FILE_TYPES)}")

    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > MAX_UPLOAD_BYTES:
        raise ValidationError("File exceeds the 25MB upload limit")
    if size == 0:
        raise ValidationError("Uploaded file is empty")

    extension = {"csv": ".csv", "json": ".json", "excel": ".xlsx"}[file_type]
    stored_name = f"{uuid.uuid4()}{extension}"
    file_path = os.path.join(_upload_dir(), stored_name)
    file_storage.save(file_path)

    dataset = Dataset(
        project_id=project_id,
        file_type=file_type,
        file_path=file_path,
        original_filename=file_storage.filename,
        status=Dataset.STATUS_UPLOADED,
        uploaded_by=uploaded_by,
    )
    db.session.add(dataset)
    db.session.commit()
    return dataset


def get_preview(dataset):
    columns, rows = read_columns_and_rows(dataset.file_path, dataset.file_type)
    return {"columns": columns, "rows": rows[:PREVIEW_ROW_LIMIT], "totalRows": len(rows)}


def map_columns(dataset, mapping):
    if "text" not in mapping or not mapping["text"]:
        raise ValidationError("A 'text' column mapping is required")

    unknown_fields = set(mapping.keys()) - set(MAPPABLE_FIELDS)
    if unknown_fields:
        raise ValidationError(f"Unknown mapping field(s): {', '.join(sorted(unknown_fields))}")

    columns, _ = read_columns_and_rows(dataset.file_path, dataset.file_type)
    unknown_columns = set(mapping.values()) - set(columns)
    if unknown_columns:
        raise ValidationError(f"Mapped column(s) not found in file: {', '.join(sorted(unknown_columns))}")

    dataset.column_mapping = mapping
    db.session.commit()
    return dataset


def _parse_rating(raw_value):
    if raw_value is None or str(raw_value).strip() == "":
        return None, True
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None, False
    if not (0 <= value <= 5):
        return None, False
    return value, True


def _parse_date(raw_value):
    if raw_value is None or str(raw_value).strip() == "":
        return None
    if isinstance(raw_value, datetime):
        return raw_value.date()
    if isinstance(raw_value, date):
        return raw_value
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(str(raw_value).strip(), fmt).date()
        except ValueError:
            continue
    return None  # unparseable date doesn't invalidate the row, just left blank


def _extract_rows(dataset, existing_text_hashes):
    """Parses the file and classifies every row as valid/invalid/duplicate.

    Returns (valid_rows, error_samples) where valid_rows is a list of dicts
    ready for Review(**dict) (excluding duplicates, which are included but
    flagged is_duplicate=True — duplicates are still imported so a human can
    review/remove them per FR-23, not silently dropped).
    """
    if not dataset.column_mapping:
        raise ValidationError("Column mapping must be saved before validating")

    mapping = dataset.column_mapping
    _, rows = read_columns_and_rows(dataset.file_path, dataset.file_type)

    valid_rows = []
    error_samples = []
    seen_hashes = set(existing_text_hashes)

    for idx, raw_row in enumerate(rows):
        row_number = idx + 2  # 1-indexed + header row
        raw_text = raw_row.get(mapping["text"]) if mapping.get("text") else None
        text = clean_text(raw_text)
        if not text:
            if len(error_samples) < MAX_ERROR_SAMPLES:
                error_samples.append({"row": row_number, "reason": "text is empty"})
            continue

        rating, rating_ok = _parse_rating(raw_row.get(mapping["rating"])) if mapping.get("rating") else (None, True)
        if not rating_ok:
            if len(error_samples) < MAX_ERROR_SAMPLES:
                error_samples.append({"row": row_number, "reason": "rating must be between 0 and 5"})
            continue

        review_date = _parse_date(raw_row.get(mapping["date"])) if mapping.get("date") else None
        source = raw_row.get(mapping["source"]) if mapping.get("source") else None

        text_hash = normalize_for_dedup(text)
        is_duplicate = text_hash in seen_hashes
        seen_hashes.add(text_hash)

        valid_rows.append({
            "text": text,
            "rating": rating,
            "review_date": review_date,
            "source": str(source) if source else None,
            "is_duplicate": is_duplicate,
        })

    return valid_rows, error_samples


def validate_dataset(dataset):
    existing_hashes = {
        normalize_for_dedup(r.text)
        for r in Review.query.filter_by(project_id=dataset.project_id).filter(
            Review.deleted_at.is_(None)
        ).all()
    }
    valid_rows, error_samples = _extract_rows(dataset, existing_hashes)

    _, raw_rows = read_columns_and_rows(dataset.file_path, dataset.file_type)
    duplicate_count = sum(1 for r in valid_rows if r["is_duplicate"])

    dataset.row_count = len(raw_rows)
    dataset.valid_row_count = len(valid_rows)
    dataset.invalid_row_count = len(raw_rows) - len(valid_rows)
    dataset.duplicate_row_count = duplicate_count
    dataset.processing_error = json.dumps(error_samples) if error_samples else None
    dataset.status = Dataset.STATUS_VALIDATED if valid_rows else Dataset.STATUS_FAILED
    db.session.commit()
    return dataset


def process_dataset(dataset):
    if dataset.status != Dataset.STATUS_VALIDATED:
        raise ValidationError("Dataset must be validated (with at least one valid row) before processing")

    existing_hashes = {
        normalize_for_dedup(r.text)
        for r in Review.query.filter_by(project_id=dataset.project_id).filter(
            Review.deleted_at.is_(None)
        ).all()
    }
    valid_rows, _ = _extract_rows(dataset, existing_hashes)

    try:
        for row in valid_rows:
            db.session.add(Review(
                project_id=dataset.project_id,
                dataset_id=dataset.id,
                text=row["text"],
                rating=row["rating"],
                review_date=row["review_date"],
                source=row["source"],
                is_duplicate=row["is_duplicate"],
            ))
        dataset.status = Dataset.STATUS_PROCESSED
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        dataset.status = Dataset.STATUS_FAILED
        dataset.processing_error = json.dumps([{"row": None, "reason": str(exc)}])
        db.session.commit()
        raise
    return dataset


def delete_dataset(dataset):
    from datetime import timezone
    dataset.deleted_at = datetime.now(timezone.utc)
    db.session.commit()
