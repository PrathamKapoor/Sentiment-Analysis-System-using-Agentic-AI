from flask import Blueprint, request, g

from app.schemas.data_source_schemas import CreateDataSourceSchema, UpdateDataSourceSchema
from app.schemas.collection_schemas import PreviewSourceSchema, CollectSourceSchema
from app.decorators.auth import (
    project_access_required, permission_required, data_source_access_required,
)
from app.services import data_source_service, collection_service
from app.services.audit_service import log_action
from app.extensions import db
from app.utils.responses import success_response

# Nested under /projects/{project_id}/sources
project_sources_bp = Blueprint("project_sources", __name__)

# Top-level /sources/{source_id}, per the approved REST API Specification
sources_bp = Blueprint("sources", __name__)


@project_sources_bp.route("", methods=["GET"])
@project_access_required
def list_sources(project_id):
    sources = data_source_service.list_sources(project_id)
    return success_response({"items": [s.to_dict() for s in sources]})


@project_sources_bp.route("", methods=["POST"])
@project_access_required
@permission_required("manage_data_sources")
def create_source(project_id):
    data = CreateDataSourceSchema().load(request.get_json(force=True) or {})
    source = data_source_service.create_source(project_id, data)
    log_action(g.current_organisation_id, g.current_user.id, "data_source.create", "data_source", source.id, {"type": source.type})
    db.session.commit()
    return success_response(source.to_dict(), message="Data source created", status_code=201)


@sources_bp.route("/<source_id>", methods=["PATCH"])
@data_source_access_required
@permission_required("manage_data_sources")
def update_source(source_id):
    data = UpdateDataSourceSchema().load(request.get_json(force=True) or {})
    source = data_source_service.update_source(g.current_data_source, data)
    log_action(g.current_organisation_id, g.current_user.id, "data_source.update", "data_source", source.id, data)
    db.session.commit()
    return success_response(source.to_dict(), message="Data source updated")


@sources_bp.route("/<source_id>", methods=["DELETE"])
@data_source_access_required
@permission_required("manage_data_sources")
def delete_source(source_id):
    source_id_str = str(g.current_data_source.id)
    data_source_service.delete_source(g.current_data_source)
    log_action(g.current_organisation_id, g.current_user.id, "data_source.delete", "data_source", source_id_str)
    db.session.commit()
    return success_response(message="Data source deleted")


@sources_bp.route("/<source_id>/test-connection", methods=["POST"])
@data_source_access_required
@permission_required("manage_data_sources")
def test_connection(source_id):
    result = collection_service.test_connection(g.current_data_source, g.current_user.id)
    return success_response(result)


@sources_bp.route("/<source_id>/preview", methods=["POST"])
@data_source_access_required
@permission_required("manage_data_sources")
def preview_source(source_id):
    data = PreviewSourceSchema().load(request.get_json(silent=True) or {})
    preview = collection_service.preview_source(g.current_data_source, g.current_user.id, options=data)
    return success_response(preview)


@sources_bp.route("/<source_id>/collect", methods=["POST"])
@data_source_access_required
@permission_required("manage_data_sources")
def collect_source(source_id):
    data = CollectSourceSchema().load(request.get_json(silent=True) or {})
    summary = collection_service.collect_source(g.current_data_source, g.current_user.id, trigger_type="manual", options=data)
    return success_response(summary, message="Collection completed")


@sources_bp.route("/<source_id>/collection-status", methods=["GET"])
@data_source_access_required
@permission_required("view_reviews")
def collection_status(source_id):
    status = collection_service.get_collection_status(g.current_data_source)
    return success_response(status)


@sources_bp.route("/<source_id>/collection-history", methods=["GET"])
@data_source_access_required
@permission_required("view_reviews")
def collection_history(source_id):
    history = collection_service.get_collection_history(g.current_data_source)
    return success_response({"items": history})


@project_sources_bp.route("/collect-enabled", methods=["POST"])
@project_access_required
@permission_required("manage_data_sources")
def collect_enabled(project_id):
    results = collection_service.collect_enabled_sources_for_project(project_id, g.current_user.id)
    return success_response({"items": results})
