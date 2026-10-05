import re
from urllib.parse import urlparse

from app.errors.exceptions import ValidationError
from app.extensions import db
from app.models import ProjectEntity


_LIST_FIELDS = {
    "aliases": "aliases",
    "includeKeywords": "include_keywords",
    "excludeKeywords": "exclude_keywords",
    "securityKeywords": "security_keywords",
    "competitorKeywords": "competitor_keywords",
    "customKeywords": "custom_keywords",
}


def _normalise_list(values, field_name):
    result = []
    seen = set()
    for value in values or []:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field_name} must contain non-empty strings")
        clean = re.sub(r"\s+", " ", value).strip()
        folded = clean.casefold()
        if folded not in seen:
            seen.add(folded)
            result.append(clean)
    return result


def _validate_canonical_url(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValidationError("canonicalUrl must be an HTTPS or HTTP URL")
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValidationError("canonicalUrl must be an HTTPS or HTTP URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError("canonicalUrl must not contain embedded credentials")
    return url


def upsert_project_entity(project, data):
    if project.deleted_at is not None:
        raise ValidationError("Cannot update an archived project entity")

    entity = ProjectEntity.query.filter_by(project_id=project.id).first()
    if entity is None:
        entity = ProjectEntity(project_id=project.id)
        db.session.add(entity)

    scalar_fields = {
        "brand": "brand", "product": "product", "model": "model", "sku": "sku",
    }
    for api_name, model_name in scalar_fields.items():
        if api_name in data:
            value = data[api_name]
            setattr(entity, model_name, value.strip() if isinstance(value, str) and value.strip() else None)

    if "canonicalUrl" in data:
        entity.canonical_url = _validate_canonical_url(data["canonicalUrl"])
    if "identifiers" in data:
        entity.identifiers = dict(data["identifiers"] or {})
    for api_name, model_name in _LIST_FIELDS.items():
        if api_name in data:
            setattr(entity, model_name, _normalise_list(data[api_name], api_name))

    if not any((entity.brand, entity.product, entity.model, entity.sku, entity.canonical_url)):
        raise ValidationError("At least one product identity field is required")

    db.session.flush()
    return entity
