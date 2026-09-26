"""CORS allowlist boundary tests.

The production CORS allowlist is a security boundary: ``README.md`` and
``docs/production_configuration_matrix.md`` both state it must be an explicit
list of exact origins and never ``""`` or ``"*"``. Flask-CORS was upgraded
5.x -> 6.x to clear PYSEC-2026-1383/1384/1385, which is a *major* bump, so
these tests pin the behaviour that must survive it:

  * a non-allowlisted Origin gets no ``Access-Control-Allow-Origin``;
  * an allowlisted Origin is echoed back exactly, never wildcarded;
  * credentials are permitted, because the API is JWT-bearing;
  * the allowlist is scoped to ``/api/*`` and not applied globally;
  * an unset allowlist falls back to the single ``FRONTEND_URL`` origin.

No other test touched CORS, so a regression here would be silent.
"""
import os
import subprocess
import sys
from contextlib import contextmanager

import pytest
from sqlalchemy.pool import StaticPool

from app import create_app
from app.config import ProductionConfig, config_by_name
from app.extensions import db as _db

ALLOWED = "https://app.example.com"
EVIL = "https://evil.example.net"
FALLBACK = "https://fallback.example.com"


def _allow_origin(response):
    return response.headers.get("Access-Control-Allow-Origin")


@contextmanager
def _production_cors_app(allowed_origins):
    """A real production-configured app with a controlled CORS allowlist.

    ``config_by_name["production"]`` is swapped for a subclass that only
    replaces the pieces a test cannot supply (a SQLAlchemy URI, and the
    engine options Postgres-only pools would need). Everything the CORS
    branch actually reads -- ``CORS_ORIGINS`` and ``FRONTEND_URL`` -- comes
    from the real :class:`ProductionConfig` attribute names, and the app is
    still built with ``config_name == "production"`` so the production
    branch in ``create_app`` is the one under test.
    """
    cls = type(
        "_CorsTestProductionConfig",
        (ProductionConfig,),
        {
            "TESTING": True,
            "RATE_LIMIT_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            },
            "CORS_ORIGINS": allowed_origins,
            "FRONTEND_URL": FALLBACK,
        },
    )
    original = config_by_name["production"]
    config_by_name["production"] = cls
    # ProductionConfig.validate_environment() reads these from the real
    # environment and also refuses the "change-me"/"dev-" defaults, so they
    # have to be present and non-default for create_app to proceed at all.
    previous_env = {
        k: os.environ.get(k)
        for k in ("DATABASE_URL", "SECRET_KEY", "JWT_SECRET_KEY")
    }
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["SECRET_KEY"] = "cors-test-secret-not-used-for-auth-32b"
    os.environ["JWT_SECRET_KEY"] = "cors-test-jwt-secret-not-used-32b"
    try:
        application = create_app("production")
        with application.app_context():
            _db.create_all()
            yield application
            _db.session.remove()
            _db.drop_all()
    finally:
        for k, v in previous_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        config_by_name["production"] = original


def test_disallowed_origin_receives_no_allow_origin_header():
    with _production_cors_app([ALLOWED]) as application:
        response = application.test_client().get(
            "/api/v1/health", headers={"Origin": EVIL}
        )
        assert response.status_code == 200
        assert _allow_origin(response) is None, (
            "a non-allowlisted origin must not be granted CORS access"
        )


def test_allowlisted_origin_is_echoed_exactly():
    with _production_cors_app([ALLOWED]) as application:
        response = application.test_client().get(
            "/api/v1/health", headers={"Origin": ALLOWED}
        )
        assert response.status_code == 200
        assert _allow_origin(response) == ALLOWED
        assert _allow_origin(response) != "*", (
            "the allowlist must never degrade to a wildcard"
        )


def test_multiple_allowlisted_origins_are_each_permitted():
    second = "https://second.example.com"
    with _production_cors_app([ALLOWED, second]) as application:
        client = application.test_client()
        for origin in (ALLOWED, second):
            response = client.get("/api/v1/health", headers={"Origin": origin})
            assert _allow_origin(response) == origin
        denied = client.get("/api/v1/health", headers={"Origin": EVIL})
        assert _allow_origin(denied) is None


def test_credentials_are_allowed_for_allowlisted_origin():
    """The API carries JWTs, so the allowlist must still permit credentials."""
    with _production_cors_app([ALLOWED]) as application:
        response = application.test_client().get(
            "/api/v1/health", headers={"Origin": ALLOWED}
        )
        assert response.headers.get("Access-Control-Allow-Credentials") == "true"


def test_allowlist_is_scoped_to_api_paths_only():
    """CORS is configured for /api/* only, so other paths get no header."""
    with _production_cors_app([ALLOWED]) as application:
        response = application.test_client().get(
            "/", headers={"Origin": ALLOWED}
        )
        assert _allow_origin(response) is None, (
            "the CORS allowlist must not be applied outside /api/*"
        )


def test_preflight_from_allowlisted_origin_is_accepted():
    with _production_cors_app([ALLOWED]) as application:
        response = application.test_client().options(
            "/api/v1/health",
            headers={"Origin": ALLOWED, "Access-Control-Request-Method": "GET"},
        )
        assert response.status_code in (200, 204)
        assert _allow_origin(response) == ALLOWED


def test_preflight_from_disallowed_origin_is_not_granted():
    with _production_cors_app([ALLOWED]) as application:
        response = application.test_client().options(
            "/api/v1/health",
            headers={"Origin": EVIL, "Access-Control-Request-Method": "GET"},
        )
        assert _allow_origin(response) != ALLOWED


def test_empty_allowlist_falls_back_to_frontend_url_not_wildcard():
    """An empty production allowlist falls back to FRONTEND_URL, never '*'."""
    with _production_cors_app([]) as application:
        client = application.test_client()
        allowed = client.get(
            "/api/v1/health", headers={"Origin": FALLBACK}
        )
        assert _allow_origin(allowed) == FALLBACK
        denied = client.get("/api/v1/health", headers={"Origin": EVIL})
        assert _allow_origin(denied) is None, (
            "an empty allowlist must fall back to FRONTEND_URL, never to '*'"
        )


def test_development_app_allows_only_the_frontend_origin(client):
    """The dev/testing app is scoped to FRONTEND_URL, not '*'."""
    response = client.get("/api/v1/health", headers={"Origin": EVIL})
    assert _allow_origin(response) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://a.example.com", ["https://a.example.com"]),
        (
            "https://a.example.com, https://b.example.com",
            ["https://a.example.com", "https://b.example.com"],
        ),
        # whitespace around a comma-separated entry must not break the match
        (
            "  https://a.example.com ,https://b.example.com  ",
            ["https://a.example.com", "https://b.example.com"],
        ),
        ("", []),
    ],
)
def test_cors_allowed_origins_env_is_parsed(raw, expected):
    """CORS_ALLOWED_ORIGINS -> ProductionConfig.CORS_ORIGINS.

    ``ProductionConfig`` reads the environment at import time, so this runs
    in a subprocess to avoid mutating the already-imported module in this
    test session.
    """
    code = (
        "from app.config import ProductionConfig;"
        "print(ProductionConfig.CORS_ORIGINS)"
    )
    env = dict(os.environ)
    env["FLASK_ENV"] = "production"
    env["DATABASE_URL"] = "sqlite:///:memory:"
    env["SECRET_KEY"] = "cors-test-secret-not-used-for-auth-32b"
    env["JWT_SECRET_KEY"] = "cors-test-jwt-secret-not-used-32b"
    env["CORS_ALLOWED_ORIGINS"] = raw
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == repr(expected)
