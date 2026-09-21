"""Per-project aspect vocabulary service.

CRUD for ``ProjectAspectVocabulary`` rows, plus the helper the aspect
analyzer uses to build the effective vocabulary for a project.

The global 13-aspect seed dictionary in ``app/services/aspect_config.py``
is never modified. The project rows are an *overlay*: the effective
vocabulary is the union of (a) active project rows (if any) and (b) the
global seed terms, merged with a lowercase-key dedup. If the project has
no rows, only the global seed apply — the pre-existing behaviour, exactly.
"""
from app.extensions import db
from app.errors.exceptions import ValidationError, ConflictError, NotFoundError
from app.models import ProjectAspectVocabulary
from app.services.aspect_config import ASPECT_SEED_TERMS, ASPECT_SYNONYMS

MAX_SURFACE_FORMS = 50
MAX_CANONICAL_LENGTH = 150
MAX_SURFACE_LENGTH = 150
MAX_ITEMS_PER_PROJECT = 100


def _normalize_and_validate(canonical_name, surface_forms):
    if not canonical_name or not canonical_name.strip():
        raise ValidationError("canonicalName must be non-empty")
    canonical = canonical_name.strip()
    if len(canonical) > MAX_CANONICAL_LENGTH:
        raise ValidationError(f"canonicalName exceeds {MAX_CANONICAL_LENGTH} characters")
    if not surface_forms:
        raise ValidationError("At least one surface form is required")
    if not isinstance(surface_forms, list):
        raise ValidationError("surfaceForms must be a list of strings")
    if len(surface_forms) > MAX_SURFACE_FORMS:
        raise ValidationError(f"Too many surface forms — limit is {MAX_SURFACE_FORMS}")
    normalized = []
    seen = set()
    for s in surface_forms:
        if not isinstance(s, str) or not s.strip():
            raise ValidationError("Each surface form must be a non-empty string")
        form = s.strip()
        if len(form) > MAX_SURFACE_LENGTH:
            raise ValidationError(f"A surface form exceeds {MAX_SURFACE_LENGTH} characters")
        lower = form.lower()
        if lower not in seen:
            seen.add(lower)
            normalized.append(form)
    # Ensure the canonical name itself is included as a surface form at
    # least once; the analyzer lowers surface forms, so this matters.
    if canonical.lower() not in seen:
        normalized.insert(0, canonical)
    return canonical, normalized


def effective_vocab_for_project(project_id):
    """Return the effective ``surface -> canonical`` map for a project.

    Merges the project's active rows with the global seed dictionary.
    Project rows win on lowercased-surface collisions. Deterministic
    ordering by creation time ensures that overlapping surfaces resolve
    consistently.
    """
    # Start from global seed (copy — the global dict is a module constant).
    effective = dict(ASPECT_SYNONYMS)
    # Overlay active project rows (project wins on overlap).
    rows = ProjectAspectVocabulary.query.filter_by(project_id=project_id).order_by(
        ProjectAspectVocabulary.created_at.asc()
    ).all()
    for row in rows:
        if not row.is_active or not row.surface_forms:
            continue
        for form in row.surface_forms:
            effective[form.strip().lower()] = row.canonical_name
    return effective


def list_vocabulary(project_id):
    return ProjectAspectVocabulary.query.filter_by(project_id=project_id).order_by(
        ProjectAspectVocabulary.canonical_name.asc()
    ).all()


def create_vocabulary_item(project_id, canonical_name, surface_forms):
    canonical, surfaces = _normalize_and_validate(canonical_name, surface_forms)
    count = ProjectAspectVocabulary.query.filter_by(project_id=project_id).count()
    if count >= MAX_ITEMS_PER_PROJECT:
        raise ValidationError("This project has reached the aspect-vocabulary limit")
    existing = ProjectAspectVocabulary.query.filter_by(
        project_id=project_id, canonical_name=canonical,
    ).first()
    if existing:
        raise ConflictError(f"An aspect named '{canonical}' already exists for this project")
    item = ProjectAspectVocabulary(
        project_id=project_id,
        canonical_name=canonical,
        surface_forms=surfaces,
    )
    db.session.add(item)
    db.session.commit()
    return item


def update_vocabulary_item(item, canonical_name=None, surface_forms=None, is_active=None):
    if canonical_name is not None:
        cleaned = canonical_name.strip()
        if not cleaned:
            raise ValidationError("canonicalName must be non-empty")
        if cleaned != item.canonical_name:
            clash = ProjectAspectVocabulary.query.filter_by(
                project_id=item.project_id, canonical_name=cleaned,
            ).first()
            if clash and clash.id != item.id:
                raise ConflictError(f"An aspect named '{cleaned}' already exists for this project")
            item.canonical_name = cleaned
    if surface_forms is not None:
        _, surfaces = _normalize_and_validate(item.canonical_name, surface_forms)
        item.surface_forms = surfaces
    if is_active is not None:
        item.is_active = bool(is_active)
    db.session.commit()
    return item


def delete_vocabulary_item(item):
    db.session.delete(item)
    db.session.commit()
