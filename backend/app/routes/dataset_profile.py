from flask import Blueprint, g

from app.decorators.auth import dataset_access_required, permission_required
from app.utils.responses import success_response

datasets_profile_bp = Blueprint("datasets_profile", __name__)

# Read-only profile — view_reviews is the broadest analytical permission
# already used for dataset validation results and trend reads. No new
# permission is needed and the tenant scope is enforced by
# dataset_access_required (re-derives project.organisation_id from DB).
@datasets_profile_bp.route("/<dataset_id>/profile", methods=["GET"])
@dataset_access_required
@permission_required("view_reviews")
def get_dataset_profile(dataset_id):
    profile = g.current_dataset.profile_report
    # Lazy compute: if the dataset was validated before the profile column
    # existed (NULL) we compute it on demand and persist it. This keeps the
    # response complete without requiring a separate "recompute profile"
    # endpoint for the minimal Phase 8 need.
    if profile is None:
        try:
            from app.services.dataset_profile_service import build_dataset_profile
            from datetime import datetime, timezone
            from app.extensions import db
            profile = build_dataset_profile(g.current_dataset)
            g.current_dataset.profile_report = profile
            g.current_dataset.profile_computed_at = datetime.now(timezone.utc)
            db.session.commit()
        except Exception:
            return success_response({"profile": None, "message": "Profile could not be computed for this dataset."})
    return success_response({"profile": profile})
