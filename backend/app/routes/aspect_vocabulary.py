from flask import Blueprint, request, g

from app.decorators.auth import project_access_required, permission_required
from app.schemas.project_aspect_vocabulary_schemas import (
    CreateAspectVocabularySchema, UpdateAspectVocabularySchema,
)
from app.services import project_aspect_vocabulary_service as vocab_service
from app.utils.responses import success_response
from app.errors.exceptions import NotFoundError
from app.models import ProjectAspectVocabulary

project_aspect_vocab_bp = Blueprint("project_aspect_vocab", __name__)


@project_aspect_vocab_bp.route("", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def list_vocabulary(project_id):
    items = vocab_service.list_vocabulary(project_id)
    return success_response({"items": [i.to_dict() for i in items]})


@project_aspect_vocab_bp.route("", methods=["POST"])
@project_access_required
@permission_required("manage_data_sources")
def create_vocabulary_item(project_id):
    data = CreateAspectVocabularySchema().load(request.get_json(force=True) or {})
    item = vocab_service.create_vocabulary_item(
        project_id, data["canonicalName"], data["surfaceForms"],
    )
    return success_response(item.to_dict(), message="Aspect added", status_code=201)


def _get_vocab_item_or_404(project_id, vocab_id):
    from app.utils.query_helpers import is_valid_uuid
    if not is_valid_uuid(vocab_id):
        raise NotFoundError("Aspect vocabulary item not found")
    item = ProjectAspectVocabulary.query.filter_by(id=vocab_id, project_id=project_id).first()
    if item is None:
        raise NotFoundError("Aspect vocabulary item not found")
    return item


@project_aspect_vocab_bp.route("/<vocab_id>", methods=["PATCH"])
@project_access_required
@permission_required("manage_data_sources")
def update_vocabulary_item(project_id, vocab_id):
    item = _get_vocab_item_or_404(project_id, vocab_id)
    data = UpdateAspectVocabularySchema().load(request.get_json(force=True) or {})
    updated = vocab_service.update_vocabulary_item(
        item,
        canonical_name=data.get("canonicalName"),
        surface_forms=data.get("surfaceForms"),
        is_active=data.get("isActive"),
    )
    return success_response(updated.to_dict(), message="Aspect updated")


@project_aspect_vocab_bp.route("/<vocab_id>", methods=["DELETE"])
@project_access_required
@permission_required("manage_data_sources")
def delete_vocabulary_item(project_id, vocab_id):
    item = _get_vocab_item_or_404(project_id, vocab_id)
    vocab_service.delete_vocabulary_item(item)
    return success_response(message="Aspect removed")
