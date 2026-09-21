"""Project website URL + cached extraction endpoints.

All routes are project-scoped via ``project_access_required`` so a
project UUID from another organisation returns 404 (not 403). The
``edit_project`` permission is required to set or clear the URL;
``view_reviews`` is enough to read the cached context.
"""
from flask import Blueprint, g, request

from app.decorators.auth import project_access_required, permission_required
from app.services import project_website_service
from app.utils.responses import success_response

project_website_bp = Blueprint("project_website", __name__)


@project_website_bp.route("/context", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def get_context(project_id):
    ctx = project_website_service.get_website_context(g.current_project)
    return success_response({"context": ctx})


@project_website_bp.route("/context", methods=["PUT"])
@project_access_required
@permission_required("edit_project")
def set_context(project_id):
    """Set or clear the project's website URL.

    Body:
      {
        "websiteUrl": "https://example.com" | null,
        "autoRefresh": false   // optional, default false
      }
    """
    data = request.get_json(force=True) or {}
    url = data.get("websiteUrl")
    auto_refresh = bool(data.get("autoRefresh", False))
    result = project_website_service.set_website_url(
        g.current_project, g.current_user.id, url, auto_refresh=auto_refresh,
    )
    return success_response({"context": result})


@project_website_bp.route("/context/refresh", methods=["POST"])
@project_access_required
@permission_required("edit_project")
def refresh_context(project_id):
    result = project_website_service.refresh_website_context(
        g.current_project, g.current_user.id,
    )
    return success_response({"context": result})
