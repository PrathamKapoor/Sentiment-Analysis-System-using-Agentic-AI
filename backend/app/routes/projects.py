from flask import Blueprint, request, g, current_app
from datetime import datetime, timezone

from app.extensions import db
from app.schemas.project_schemas import (
    CreateProjectSchema, UpdateProjectSchema, AddProjectMemberSchema, ArchiveProjectSchema,
)
from app.schemas.project_entity_schemas import ProjectEntitySchema
from app.decorators.auth import (
    organisation_member_required, permission_required, project_access_required,
)
from app.services import project_service
from app.services.audit_service import log_action
from app.utils.responses import success_response
from app.errors.exceptions import ValidationError, NotFoundError, ConflictError

projects_bp = Blueprint("projects", __name__)


@projects_bp.route("", methods=["GET"])
@organisation_member_required
def list_projects():
    status = request.args.get("status")
    search = request.args.get("search")
    projects = project_service.list_projects(g.current_organisation_id, status, search)
    return success_response({"items": [p.to_dict() for p in projects]})


@projects_bp.route("", methods=["POST"])
@organisation_member_required
@permission_required("create_project")
def create_project():
    data = CreateProjectSchema().load(request.get_json(force=True) or {})
    project = project_service.create_project(g.current_organisation_id, g.current_user.id, data)
    log_action(g.current_organisation_id, g.current_user.id, "project.create", "project", project.id, {"name": project.name})
    db.session.commit()
    return success_response(project.to_dict(), message="Project created", status_code=201)


@projects_bp.route("/<project_id>", methods=["GET"])
@project_access_required
def get_project(project_id):
    return success_response(g.current_project.to_dict())


@projects_bp.route("/<project_id>/entity", methods=["GET"])
@project_access_required
def get_project_entity(project_id):
    from app.models import ProjectEntity
    from app.services.entity_resolver import resolve_project_entity

    entity = ProjectEntity.query.filter_by(project_id=project_id).first()
    if entity is None:
        return success_response(resolve_project_entity(g.current_project))
    return success_response(entity.to_dict())


@projects_bp.route("/<project_id>/entity", methods=["PUT"])
@project_access_required
@permission_required("edit_project")
def put_project_entity(project_id):
    from app.services.project_entity_service import upsert_project_entity

    data = ProjectEntitySchema().load(request.get_json(force=True) or {})
    entity = upsert_project_entity(g.current_project, data)
    log_action(
        g.current_organisation_id, g.current_user.id,
        "project.entity_updated", "project", project_id,
        {"hasCanonicalUrl": bool(entity.canonical_url), "keywordGroups": {
            "include": len(entity.include_keywords or []),
            "exclude": len(entity.exclude_keywords or []),
            "security": len(entity.security_keywords or []),
            "competitor": len(entity.competitor_keywords or []),
            "custom": len(entity.custom_keywords or []),
        }},
    )
    db.session.commit()
    return success_response(entity.to_dict(), message="Project entity saved")


@projects_bp.route("/<project_id>/entity/discover", methods=["POST"])
@project_access_required
@permission_required("edit_project")
def discover_project_entity(project_id):
    """Return reviewable entity/search suggestions; never saves model output."""
    from app.schemas.product_discovery_schemas import ProductDiscoveryRequestSchema
    from app.services.product_discovery import deterministic_discovery, discover_product_terms

    data = ProductDiscoveryRequestSchema().load(request.get_json(force=True) or {})
    if current_app.config.get("PRODUCT_DISCOVERY_LLM_ENABLED", True):
        result = discover_product_terms(
            data["description"], sku=data.get("sku"),
            canonical_url=data.get("canonicalUrl"), identifiers=data.get("identifiers"),
        )
    else:
        result = deterministic_discovery(
            data["description"], data.get("identifiers"), sku=data.get("sku"),
            canonical_url=data.get("canonicalUrl"),
        )
    log_action(g.current_organisation_id, g.current_user.id,
               "project.entity_discovery_suggested", "project", project_id,
               {"providerRole": result.get("provider_role"), "status": result.get("status")})
    db.session.commit()
    return success_response({
        "canonicalName": result["canonical_name"], "brand": result["brand"],
        "product": result["product"], "model": result["model"],
        "aliases": result["aliases"], "searchKeywords": result["search_keywords"],
        "identityConstraints": result["identity_constraints"],
        "excludeKeywords": result["exclude_keywords"],
        "includeKeywords": result["include_keywords"],
        "securityKeywords": result["security_keywords"],
        "competitorKeywords": result["competitor_keywords"],
        "customKeywords": result["custom_keywords"],
        "identifiers": result["identifiers"],
        "provider": result["provider"], "providerRole": result["provider_role"],
        "providerModel": result["model_name"],
        "status": result["status"],
    }, message="Product identity suggestions generated")


@projects_bp.route("/<project_id>/security-findings", methods=["GET"])
@project_access_required
def list_project_security_findings(project_id):
    from app.models import SecurityFinding

    findings = SecurityFinding.query.filter_by(
        project_id=project_id, organisation_id=g.current_organisation_id
    ).order_by(SecurityFinding.created_at.desc()).limit(500).all()
    return success_response({"items": [finding.to_dict() for finding in findings]})


@projects_bp.route("/<project_id>/security-findings/analyze", methods=["POST"])
@project_access_required
@permission_required("review_security_findings")
def analyze_project_security_findings(project_id):
    from app.services.security_intelligence_service import analyze_project_security_signals

    result = analyze_project_security_signals(g.current_project)
    log_action(g.current_organisation_id, g.current_user.id,
               "security_findings.analyzed", "project", project_id, result)
    db.session.commit()
    return success_response(result, message="Security signal analysis completed")


@projects_bp.route("/<project_id>/security-findings/<finding_id>", methods=["PATCH"])
@project_access_required
@permission_required("review_security_findings")
def review_project_security_finding(project_id, finding_id):
    from app.models import SecurityFinding

    payload = request.get_json(force=True) or {}
    status = payload.get("status")
    notes = payload.get("analystNotes")
    if status not in {"confirmed", "dismissed"}:
        raise ValidationError("status must be confirmed or dismissed by a human reviewer")
    if notes is not None and (not isinstance(notes, str) or len(notes) > 2000):
        raise ValidationError("analystNotes must be a string no longer than 2000 characters")
    finding = SecurityFinding.query.filter_by(
        id=finding_id, project_id=project_id, organisation_id=g.current_organisation_id
    ).first()
    if finding is None:
        raise NotFoundError("Security finding not found")
    if finding.status == "stale":
        raise ConflictError("This finding no longer matches the current eligible review text. Re-run analysis before human review.")
    finding.status = status
    finding.analyst_notes = notes.strip() if isinstance(notes, str) and notes.strip() else None
    finding.reviewed_by = g.current_user.id
    finding.reviewed_at = datetime.now(timezone.utc)
    log_action(g.current_organisation_id, g.current_user.id,
               "security_finding.reviewed", "security_finding", finding.id,
               {"status": status})
    db.session.commit()
    return success_response(finding.to_dict(), message="Security finding reviewed")


@projects_bp.route("/<project_id>", methods=["PATCH"])
@project_access_required
@permission_required("edit_project")
def update_project(project_id):
    data = UpdateProjectSchema().load(request.get_json(force=True) or {})
    project = project_service.update_project(g.current_project, data)
    log_action(g.current_organisation_id, g.current_user.id, "project.update", "project", project.id, data)
    db.session.commit()
    return success_response(project.to_dict(), message="Project updated")


@projects_bp.route("/<project_id>", methods=["DELETE"])
@project_access_required
@permission_required("delete_project")
def delete_project(project_id):
    project_service.soft_delete_project(g.current_project)
    log_action(g.current_organisation_id, g.current_user.id, "project.delete", "project", project_id)
    db.session.commit()
    return success_response(message="Project deleted")


@projects_bp.route("/<project_id>/archive", methods=["POST"])
@project_access_required
@permission_required("edit_project")
def archive_project(project_id):
    data = ArchiveProjectSchema().load(request.get_json(force=True) or {})
    project = project_service.archive_project(g.current_project, data["archived"])
    log_action(
        g.current_organisation_id, g.current_user.id,
        "project.archive" if data["archived"] else "project.unarchive",
        "project", project.id,
    )
    db.session.commit()
    return success_response(project.to_dict(), message="Project status updated")


@projects_bp.route("/<project_id>/members", methods=["GET"])
@project_access_required
def list_project_members(project_id):
    members = project_service.list_project_members(project_id)
    return success_response({"items": [
        {"userId": str(m.user_id), "user": m.user.to_dict() if m.user else None} for m in members
    ]})


@projects_bp.route("/<project_id>/members", methods=["POST"])
@project_access_required
@permission_required("edit_project")
def add_project_member(project_id):
    data = AddProjectMemberSchema().load(request.get_json(force=True) or {})
    member = project_service.add_project_member(project_id, g.current_organisation_id, data["userId"])
    log_action(g.current_organisation_id, g.current_user.id, "project.member.add", "project", project_id, {"userId": data["userId"]})
    db.session.commit()
    return success_response({"userId": str(member.user_id)}, message="Member added", status_code=201)


@projects_bp.route("/<project_id>/members/<user_id>", methods=["DELETE"])
@project_access_required
@permission_required("edit_project")
def remove_project_member(project_id, user_id):
    project_service.remove_project_member(project_id, user_id)
    log_action(g.current_organisation_id, g.current_user.id, "project.member.remove", "project", project_id, {"userId": user_id})
    db.session.commit()
    return success_response(message="Member removed")
