import json
import logging
import os
from datetime import datetime, timezone

from flask import Flask

from app.config import config_by_name
from app.extensions import db, migrate, jwt, cors
from app.errors.handlers import register_error_handlers
from app.routes import register_blueprints


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    config_cls = config_by_name[config_name]
    if hasattr(config_cls, "validate_environment"):
        config_cls.validate_environment()
    app.config.from_object(config_cls)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # --- CORS -------------------------------------------------------------
    # Development: only the Vite dev server origin.
    # Production: explicit CORS_ALLOWED_ORIGINS list; empty list falls back
    #   to FRONTEND_URL so a single-origin deploy still works.
    # The trusted proxy count determines how X-Forwarded-* headers are read
    # (0 = assume the app faces the internet directly).
    if config_name == "production":
        origins = app.config.get("CORS_ORIGINS") or [app.config["FRONTEND_URL"]]
    else:
        origins = [app.config["FRONTEND_URL"]]
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": origins}},
        supports_credentials=True,
    )

    # --- Proxy headers ----------------------------------------------------
    # werkzeug.middleware.proxy_fix.ProxyFix only strips X-Forwarded-* when
    # the proxy count is >= 1. We express that explicitly so operators can
    # reason about the trust boundary.
    trusted_proxies = int(app.config.get("TRUSTED_PROXY_COUNT", 0))
    if trusted_proxies > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=trusted_proxies,
            x_proto=1,
            x_host=1,
            x_prefix=1,
        )

    # --- Logging ----------------------------------------------------------
    # Production uses structured one-line-per-log JSON records when
    # LOG_JSON is enabled; the request id is attached to every line.
    level_name = app.config.get("LOG_LEVEL", "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)
    if app.config.get("LOG_JSON", False):
        _configure_json_logging(app, level)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

    # --- Rate limiting ------------------------------------------------------
    # In-memory by default; switch REDIS_URL / RateLimitStorage for a shared
    # store when you deploy multiple workers.
    from app.limiter import create_limiter
    rate_limit_enabled = app.config.get("RATE_LIMIT_ENABLED", None)
    limiter = create_limiter(enabled=rate_limit_enabled)
    if limiter is not None:
        # init_app handles the app.extensions plumbing itself (the
        # extension registers itself into app.extensions["limiter"]).
        limiter.init_app(app)

    register_error_handlers(app)
    register_blueprints(app)

    if limiter is not None:
        from app.limiter import apply_limits
        apply_limits(app, limiter)

    from app.services.token_service import is_revoked
    from app.services.observability import get_or_create_request_id, REQUEST_ID_HEADER

    @app.before_request
    def _assign_request_id():
        get_or_create_request_id()

    @app.after_request
    def _emit_request_id(response):
        rid = get_or_create_request_id()
        if rid:
            response.headers[REQUEST_ID_HEADER] = rid
        return response

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        return is_revoked(jwt_payload["jti"])

    # Ensure models are registered with SQLAlchemy metadata before migrations run.
    from app import models  # noqa: F401

    @app.cli.command("seed")
    def seed_command():
        """Seed the fixed permission catalogue and the 6 built-in roles."""
        from app.services.seed_service import seed_permissions_and_roles
        seed_permissions_and_roles()
        print("Seeded permissions and built-in roles.")

    return app


def _configure_json_logging(app, level: int) -> None:
    """Replace the default text formatter with a one-line JSON formatter.

    Emitted JSON keys:
      timestamp (ISO-8601 UTC), level, logger, message, requestId.
    Sensitive values (passwords, tokens, keys) never appear — the logger
    only receives the fields the call site passes.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers[:] = [handler]
    root_logger.setLevel(level)


class _JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        try:
            from app.services.observability import current_request_id
            rid = current_request_id()
            if rid:
                payload["requestId"] = rid
        except Exception:
            pass
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))
