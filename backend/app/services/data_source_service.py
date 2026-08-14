from app.extensions import db
from app.errors.exceptions import ValidationError, CollectionError
from app.models import DataSource
from app.services.collectors.security import validate_url_shape
from app.services.collectors.ecommerce import normalize_ecommerce_url


def _validate_url(url):
    # Format-only check (scheme + host, rejects file://, javascript:, localhost).
    # No DNS resolution here — that's SSRF validation, which only runs right
    # before an actual network fetch (preview/test-connection/collect), not
    # on every plain CRUD save. See app/services/collectors/security.py.
    try:
        validate_url_shape(url)
    except CollectionError as exc:
        raise ValidationError(exc.message)


def normalize_keywords(keywords):
    """Trim, case-insensitively deduplicate, and ignore blank CSV entries."""
    normalized = []
    seen = set()
    for value in keywords or []:
        for part in str(value).split(","):
            keyword = " ".join(part.split()).strip()
            key = keyword.casefold()
            if keyword and key not in seen:
                seen.add(key)
                normalized.append(keyword)
    return normalized


def _normalized_source_url(source_type, url):
    return normalize_ecommerce_url(url) if source_type == "ecommerce" else url.strip()


def list_sources(project_id):
    return DataSource.query.filter_by(project_id=project_id).order_by(
        DataSource.created_at.desc()
    ).all()


def create_source(project_id, data):
    if data["type"] not in DataSource.TYPES:
        raise ValidationError(f"type must be one of: {', '.join(DataSource.TYPES)}")
    _validate_url(data["url"])
    source = DataSource(
        project_id=project_id,
        type=data["type"],
        url=_normalized_source_url(data["type"], data["url"]),
        keywords=normalize_keywords(data.get("keywords")),
    )
    db.session.add(source)
    db.session.commit()
    return source


def update_source(source, data):
    if "url" in data:
        _validate_url(data["url"])
        source.url = _normalized_source_url(source.type, data["url"])
    if "keywords" in data:
        source.keywords = normalize_keywords(data["keywords"])
    if "enabled" in data:
        source.enabled = data["enabled"]
    db.session.commit()
    return source


def delete_source(source):
    db.session.delete(source)
    db.session.commit()
