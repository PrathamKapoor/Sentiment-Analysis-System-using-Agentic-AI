import re

from flask import Blueprint, request, g, send_file

from app.schemas.report_schemas import CreateReportSchema
from app.decorators.auth import project_access_required, permission_required, report_access_required
from app.services import report_service
from app.services.audit_service import log_action
from app.extensions import db
from app.utils.responses import success_response

project_reports_bp = Blueprint("project_reports", __name__)
reports_bp = Blueprint("reports", __name__)

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@project_reports_bp.route("", methods=["GET"])
@project_access_required
@permission_required("view_reviews")
def list_reports(project_id):
    items = report_service.list_reports(project_id)
    return success_response({"items": [r.to_dict() for r in items]})


@project_reports_bp.route("", methods=["POST"])
@project_access_required
@permission_required("generate_report")
def create_report(project_id):
    data = CreateReportSchema().load(request.get_json(force=True) or {})
    report = report_service.create_report(project_id, g.current_user.id, data)
    return success_response(report.to_dict(), message="Report generated", status_code=201)


@reports_bp.route("/<report_id>", methods=["GET"])
@report_access_required
@permission_required("view_reviews")
def get_report(report_id):
    return success_response(g.current_report.to_dict())


@reports_bp.route("/<report_id>/download", methods=["GET"])
@report_access_required
@permission_required("view_reviews")
def download_report(report_id):
    # report_access_required already re-derived the file's owning project
    # from the DB (not from any client-supplied path) and confirmed it's in
    # the caller's organisation — there is no user-controlled path component
    # anywhere in this handler, which is what actually prevents path
    # traversal (the file_path itself is a server-generated UUID filename).
    file_path = report_service.get_report_file(g.current_report)

    log_action(
        g.current_organisation_id, g.current_user.id, "report.downloaded", "report", g.current_report.id,
    )
    db.session.commit()

    display_name = _SAFE_FILENAME_RE.sub("_", g.current_report.to_dict()["reportName"])
    extension = "pdf" if g.current_report.file_format == "pdf" else "xlsx"
    mimetype = "application/pdf" if g.current_report.file_format == "pdf" else \
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return send_file(
        file_path, mimetype=mimetype, as_attachment=True,
        download_name=f"{display_name}.{extension}",
    )


@reports_bp.route("/<report_id>", methods=["DELETE"])
@report_access_required
@permission_required("generate_report")
def delete_report(report_id):
    report_service.delete_report(g.current_report, g.current_user.id)
    return success_response(message="Report deleted")
