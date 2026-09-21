"""Health, liveness, and readiness endpoints.

  /health   — liveness: the process is alive. No dependency checks.
  /live     — alias for /health (Kubernetes-style)
  /ready    — readiness: the application can serve traffic (database reachable).
              Optional dependencies (LLM provider) do NOT affect readiness —
              the deterministic pipeline must continue to work when they
              are unavailable.

The endpoints intentionally never return 5xx on health checks. A failing
database yields 503 (not reachable-5xx generic error) so orchestrators
can route the instance out of rotation.
"""
from flask import Blueprint, has_app_context

from app.utils.responses import success_response

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    return success_response({"status": "ok"}, message="Service is healthy")


@health_bp.route("/live", methods=["GET"])
def liveness_check():
    return success_response({"status": "alive"}, message="Process is alive")


@health_bp.route("/ready", methods=["GET"])
def readiness_check():
    """The process can serve traffic: database is reachable.

    An optional service (LLM, website fetcher) being unavailable does NOT
    make the whole app unready — the deterministic pipeline must continue
    to work when those are down. A failure here signals orchestrators to
    stop routing traffic to this instance.
    """
    if not has_app_context():
        from app import create_app
        create_app("testing")  # defensive; should not happen
    try:
        from app.extensions import db
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
    except Exception:
        return success_response(
            {"status": "not_ready", "reason": "database unavailable"},
            message="Service is not ready",
            status_code=503,
        )
    return success_response({"status": "ready"}, message="Service is ready")
