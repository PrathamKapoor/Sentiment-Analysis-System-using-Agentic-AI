import os
from datetime import timedelta


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me-in-production-32b")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-key-change-me-in-production-32b")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    JSON_SORT_KEYS = False
    # Where uploaded datasets are stored. Defaults to <instance>/uploads if unset —
    # never hard-coded to a specific machine path.
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER") or None
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024

    # Topic analysis (TF-IDF + MiniBatchKMeans) — configurable cluster count.
    DEFAULT_TOPIC_COUNT = int(os.environ.get("DEFAULT_TOPIC_COUNT", 8))
    MAX_TOPIC_COUNT = int(os.environ.get("MAX_TOPIC_COUNT", 20))

    # Keyword extraction — extra stopwords beyond sklearn's built-in English list.
    KEYWORD_BLOCKED_WORDS = {
        w.strip().lower()
        for w in os.environ.get("KEYWORD_BLOCKED_WORDS", "").split(",")
        if w.strip()
    }

    # Recommendation generation — minimum aspect frequency before a
    # negative-sentiment aspect becomes a recommendation candidate.
    RECOMMENDATION_MIN_FREQUENCY = int(os.environ.get("RECOMMENDATION_MIN_FREQUENCY", 3))

    # Report generation — where files are written and how much raw review
    # data a single report is allowed to embed.
    REPORT_OUTPUT_DIRECTORY = os.environ.get("REPORT_OUTPUT_DIRECTORY") or None
    MAX_REPORT_REVIEW_ROWS = int(os.environ.get("MAX_REPORT_REVIEW_ROWS", 500))
    DEFAULT_ALERT_WINDOW_DAYS = int(os.environ.get("DEFAULT_ALERT_WINDOW_DAYS", 7))

    # Web-data collection (Phase 6) — every collector reads limits from here,
    # nothing is hard-coded per-collector. See README "Collection Safety".
    SCRAPER_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("SCRAPER_REQUEST_TIMEOUT_SECONDS", 15))
    SCRAPER_REQUEST_DELAY_SECONDS = float(os.environ.get("SCRAPER_REQUEST_DELAY_SECONDS", 1))
    SCRAPER_MAX_PAGES = int(os.environ.get("SCRAPER_MAX_PAGES", 10))
    SCRAPER_MAX_RECORDS = int(os.environ.get("SCRAPER_MAX_RECORDS", 500))
    SCRAPER_MAX_RESPONSE_MB = float(os.environ.get("SCRAPER_MAX_RESPONSE_MB", 5))
    SCRAPER_MAX_RETRIES = int(os.environ.get("SCRAPER_MAX_RETRIES", 2))
    SCRAPER_MAX_REDIRECTS = int(os.environ.get("SCRAPER_MAX_REDIRECTS", 5))
    SCRAPER_USER_AGENT = os.environ.get(
        "SCRAPER_USER_AGENT",
        "SentimentAnalysisSystemBot/1.0 (+data-collection; respects robots.txt)",
    )
    # DEV/TEST ONLY, default off. When true, disables the localhost/private-IP
    # SSRF block so a developer can point a source at a locally-run mock
    # server for manual testing. NEVER enable in any environment reachable
    # from the internet — see README "Collection Safety".
    #
    # SECURITY: this option is intended only for controlled local
    # development/testing and must not be exposed as an agent-controllable
    # setting. It is read exclusively from this environment variable at
    # process startup — no request body field, query param, collector
    # `options` value, or future agent/tool parameter reads or writes it.
    # If Phase 7 orchestration ever needs a "safe test mode," add a
    # separate, narrowly-scoped mechanism — do not repurpose this flag.
    SCRAPER_ALLOW_PRIVATE_TARGETS = os.environ.get("SCRAPER_ALLOW_PRIVATE_TARGETS", "false").lower() == "true"
    # Agentic orchestration engine selection.
    #   "deterministic" (default) - the original plain-Python for-loop
    #                              orchestrator in services/agents/orchestrator.py
    #   "langgraph"               - the StateGraph implementation in
    #                              services/agents/langgraph_orchestrator.py
    # Both are step-for-step equivalent and neither involves an LLM. This
    # selects *how* the workflow is walked, never *what* the agents compute.
    # Invalid values fall back to "deterministic" rather than failing the
    # request, so a typo can never take the API down.
    AGENTIC_ENGINE = (os.environ.get("AGENTIC_ENGINE") or "deterministic").strip().lower()
    if AGENTIC_ENGINE not in ("deterministic", "langgraph"):
        AGENTIC_ENGINE = "deterministic"

    # Discovery is metadata-only and disabled by default. Runtime execution
    # remains limited to manually reviewed entries in RUNTIME_REGISTRY.
    SOURCE_FALLBACK_DISCOVERY_MODE = os.environ.get("SOURCE_FALLBACK_DISCOVERY_MODE", "CURATED_ONLY")


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/sentiment_dev",
    )


class TestingConfig(BaseConfig):
    TESTING = True
    # Rate limiting is disabled in tests — the test suite exercises
    # rate-limited routes repeatedly, and the deterministic expectations
    # would otherwise flake on the 4xx that the limiter produces.
    RATE_LIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)

    # Keep the same in-memory SQLite connection alive for the whole test session
    # instead of a fresh (empty) DB per checkout.
    if "TEST_DATABASE_URL" not in os.environ:
        from sqlalchemy.pool import StaticPool

        SQLALCHEMY_ENGINE_OPTIONS = {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        }


class ProductionConfig(BaseConfig):
    """Production configuration.

    Startup fails fast when a required environment variable is missing
    rather than silently falling back to a development default. The
    required variables are documented in backend/.env.example and in
    docs/production_deployment.md.
    """
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    # Connection pool settings for PostgreSQL deployments. The pool with
    # pre_ping detects dropped/stale connections before use; recycle forces
    # periodic connection refresh so long-lived workers don't sit on dead
    # connections after idle timeout on managed Postgres.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("DB_POOL_MAX_OVERFLOW", "5")),
        "pool_pre_ping": True,
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE_SECONDS", "1800")),
    }

    # Reverse proxy behavior. TRUSTED_PROXY_COUNT = how many trusted proxy
    # layers exist in front of the app. 0 = direct internet exposure
    # (do not trust X-Forwarded-* headers at all).
    TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))

    # Production CORS: comma-separated list of exact origins. Never "" or
    # "*" — the frontend lives at a single known origin in production.
    CORS_ORIGINS = [
        origin.strip()
        for origin in (os.environ.get("CORS_ALLOWED_ORIGINS") or "").split(",")
        if origin.strip()
    ]

    # Optional metrics/logging configuration. JSON logs make parse-able
    # container output; disable only if an operator needs plain text.
    LOG_JSON = os.environ.get("LOG_JSON", "true").lower() == "true"
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    @classmethod
    def validate_environment(cls):
        """Raise early if required production environment variables are
        missing. Called from create_app() in production mode."""
        missing = []
        for required in ("DATABASE_URL", "SECRET_KEY", "JWT_SECRET_KEY"):
            if not os.environ.get(required):
                missing.append(required)
        if missing:
            raise RuntimeError(
                "Missing required production environment variables: "
                + ", ".join(missing)
                + ". See backend/.env.example and docs/production_deployment.md."
            )
        # The default dev secrets must never be used in production.
        for key_name in ("SECRET_KEY", "JWT_SECRET_KEY"):
            value = os.environ[key_name]
            if "change-me" in value or "dev-" in value:
                raise RuntimeError(
                    f"{key_name} is set to the development default; set a "
                    "strong unique value. See docs/production_deployment.md."
                )


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
