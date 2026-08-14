import logging
import os

from flask import Flask

from app.config import config_by_name
from app.extensions import db, migrate, jwt, cors
from app.errors.handlers import register_error_handlers
from app.routes import register_blueprints


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["FRONTEND_URL"]}})

    logging.basicConfig(
        level=logging.DEBUG if app.config.get("DEBUG") else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    register_error_handlers(app)
    register_blueprints(app)

    from app.services.token_service import is_revoked

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
