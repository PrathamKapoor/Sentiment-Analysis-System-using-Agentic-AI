from flask import Blueprint, request, g

from app.extensions import db
from app.schemas.project_schemas import (
    CreateProjectSchema, UpdateProjectSchema, AddProjectMemberSchema, ArchiveProjectSchema,
)
from app.decorators.auth import (
    organisation_member_required, permission_required, project_access_required,
)
from app.services import project_service
from app.services.audit_service import log_action
from app.utils.responses import success_response

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
