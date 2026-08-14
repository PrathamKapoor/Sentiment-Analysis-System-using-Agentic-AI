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
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
