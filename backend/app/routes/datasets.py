from flask import Blueprint, request, g

from app.extensions import db
from app.errors.exceptions import ValidationError
from app.schemas.dataset_schemas import MapColumnsSchema
from app.decorators.auth import (
    project_access_required, permission_required, dataset_access_required,
)
from app.services import dataset_service
from app.services.audit_service import log_action
from app.utils.responses import success_response

project_datasets_bp = Blueprint("project_datasets", __name__)
datasets_bp = Blueprint("datasets", __name__)


@project_datasets_bp.route("", methods=["GET"])
@project_access_required
def list_datasets(project_id):
    datasets = dataset_service.list_datasets(project_id)
    return success_response({"items": [d.to_dict() for d in datasets]})


@project_datasets_bp.route("", methods=["POST"])
@project_access_required
@permission_required("upload_dataset")
def upload_dataset(project_id):
    if "file" not in request.files:
        raise ValidationError("A 'file' upload is required")
    file_storage = request.files["file"]
    file_type = request.form.get("fileType")
    dataset = dataset_service.create_dataset(project_id, g.current_user.id, file_storage, file_type)
    log_action(
        g.current_organisation_id, g.current_user.id, "dataset.upload", "dataset", dataset.id,
        {"filename": dataset.original_filename},
    )
    db.session.commit()
    return success_response(
        {
            "datasetId": str(dataset.id),
            "status": dataset.status,
            "previewUrl": f"/api/v1/datasets/{dataset.id}",
        },
        message="Dataset uploaded, awaiting column mapping",
        status_code=202,
    )


@datasets_bp.route("/<dataset_id>", methods=["GET"])
@dataset_access_required
def get_dataset(dataset_id):
    body = g.current_dataset.to_dict()
    body["preview"] = dataset_service.get_preview(g.current_dataset)
    return success_response(body)


@datasets_bp.route("/<dataset_id>/map-columns", methods=["POST"])
@dataset_access_required
@permission_required("upload_dataset")
def map_columns(dataset_id):
    mapping = MapColumnsSchema().load(request.get_json(force=True) or {})
    mapping = {k: v for k, v in mapping.items() if v}
    dataset = dataset_service.map_columns(g.current_dataset, mapping)
    log_action(g.current_organisation_id, g.current_user.id, "dataset.map_columns", "dataset", dataset.id, mapping)
    db.session.commit()
    return success_response(dataset.to_dict(), message="Column mapping saved")


@datasets_bp.route("/<dataset_id>/validate", methods=["POST"])
@dataset_access_required
@permission_required("upload_dataset")
def validate_dataset(dataset_id):
    dataset = dataset_service.validate_dataset(g.current_dataset)
    log_action(g.current_organisation_id, g.current_user.id, "dataset.validate", "dataset", dataset.id, {
        "validRows": dataset.valid_row_count, "invalidRows": dataset.invalid_row_count,
    })
    db.session.commit()
    return success_response(dataset.to_dict(), message="Dataset validated", status_code=202)


@datasets_bp.route("/<dataset_id>/process", methods=["POST"])
@dataset_access_required
@permission_required("upload_dataset")
def process_dataset(dataset_id):
    dataset = dataset_service.process_dataset(g.current_dataset)
    log_action(g.current_organisation_id, g.current_user.id, "dataset.process", "dataset", dataset.id, {
        "reviewsCreated": dataset.valid_row_count,
    })
    db.session.commit()
    return success_response(
        {"jobId": str(dataset.id), "status": dataset.status, "dataset": dataset.to_dict()},
        message="Dataset processed",
        status_code=202,
    )


@datasets_bp.route("/<dataset_id>", methods=["DELETE"])
@dataset_access_required
@permission_required("upload_dataset")
def delete_dataset(dataset_id):
    dataset_id_str = str(g.current_dataset.id)
    dataset_service.delete_dataset(g.current_dataset)
    log_action(g.current_organisation_id, g.current_user.id, "dataset.delete", "dataset", dataset_id_str)
    db.session.commit()
    return success_response(message="Dataset deleted")
