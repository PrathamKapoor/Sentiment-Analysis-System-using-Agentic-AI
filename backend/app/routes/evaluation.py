from flask import Blueprint, g

from app.decorators.auth import jwt_required_custom
from app.services.evaluation_service import evaluate_benchmark
from app.utils.responses import success_response

# System-level benchmark — not tenant-scoped. Any authenticated user may
# read it. No per-project data is ever returned. The result is
# deterministic and fully recomputed on every request (the fixture is
# small), so there is nothing to cache or invalidate.
evaluation_bp = Blueprint("evaluation", __name__)


@evaluation_bp.route("/benchmark", methods=["GET"])
@jwt_required_custom
def get_benchmark():
    result = evaluate_benchmark()
    return success_response(result)
