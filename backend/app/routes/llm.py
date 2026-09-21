"""LLM provider status endpoint.

Returns a small, safe summary of the active provider. No secrets, no
key material, no full base URL. Authenticated users only.
"""
from flask import Blueprint

from app.decorators.auth import jwt_required_custom
from app.services.llm_service import provider_summary
from app.utils.responses import success_response

llm_bp = Blueprint("llm", __name__)


@llm_bp.route("/status", methods=["GET"])
@jwt_required_custom
def get_status():
    return success_response(provider_summary())
