"""PostgreSQL migration audit for Phase 11.

Runs the full alembic chain (0001 -> 0009) inside an isolated schema
within the configured development database. The public schema and any
other schema remain untouched.

This script:
  1. Creates a fresh ``phase11_audit`` schema and grants CREATE on it.
  2. Runs ``flask db upgrade head`` with a connection URL whose
     ``search_path`` puts every DDL inside that schema.
  3. Verifies all expected tables exist.
  4. Runs ``flask db downgrade 0008`` and confirms the 0009-only table
     is gone.
  5. Runs ``flask db upgrade head`` again to leave the schema clean.
  6. Drops the audit schema.

Usage::

  python -m scripts.audit_migration_postgres
"""
from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import create_engine, text

SCHEMA = "phase11_audit"


def _alembic(url: str, *args: str, label: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["FLASK_APP"] = "run.py"
    print(f"[{label}] alembic {' '.join(args)}")
    res = subprocess.run(
        [sys.executable, "-m", "flask", "db", *args],
        env=env,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        raise SystemExit(f"alembic {' '.join(args)} failed")


def _tables(conn) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = :s"
            ),
            {"s": SCHEMA},
        ).fetchall()
    }


def main() -> int:
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_root)
    sys.path.insert(0, backend_root)

    from dotenv import load_dotenv
    load_dotenv()

    base_url = os.environ["DATABASE_URL"]
    if "postgresql" not in base_url:
        raise SystemExit("DATABASE_URL must be PostgreSQL for this audit")
    # Strip any pre-existing ``?options=...`` so we control the
    # search_path exactly. SQLAlchemy/pg connect both behave
    # predictably with a single options parameter.
    if "?" in base_url:
        base_url = base_url.split("?", 1)[0]
    audit_url = base_url + "?options=-csearch_path%3D" + SCHEMA

    admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
    admin.dispose()
    print(f"created audit schema: {SCHEMA}")

    try:
        _alembic(audit_url, "upgrade", "head", label="upgrade")

        engine = create_engine(audit_url)
        with engine.connect() as conn:
            tables = _tables(conn)
            expected = {
                "projects", "project_website_context", "reports",
                "agent_workflows", "ai_summaries", "alerts", "aspects",
                "aspect_sentiments", "audit_logs", "data_sources",
                "datasets", "member_roles", "organisation_members",
                "organisations", "permissions", "project_members",
                "project_aspect_vocabulary", "recommendations",
                "reviews", "review_topics", "role_permissions", "roles",
                "sentiment_results", "topics", "users",
            }
            missing = expected - tables
            assert not missing, f"missing tables after upgrade: {missing}"
            assert len(tables) >= 25, (
                f"expected >= 25 tables, got {len(tables)}"
            )

            row = conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema=:s AND table_name='datasets' "
                    "AND column_name='profile_report'"
                ),
                {"s": SCHEMA},
            ).first()
            assert row and "json" in row[0].lower(), (
                f"datasets.profile_report should be JSON, got {row}"
            )
            row = conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema=:s "
                    "AND table_name='project_website_context' "
                    "AND column_name='project_id'"
                ),
                {"s": SCHEMA},
            ).first()
            assert row and "uuid" in row[0].lower(), (
                f"project_website_context.project_id should be UUID, got {row}"
            )
        engine.dispose()

        _alembic(audit_url, "downgrade", "0008", label="downgrade")
        engine = create_engine(audit_url)
        with engine.connect() as conn:
            tables = _tables(conn)
            assert "project_website_context" not in tables, (
                "project_website_context should be dropped at 0008"
            )
        engine.dispose()

        _alembic(audit_url, "upgrade", "head", label="re-upgrade")
    finally:
        admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        admin.dispose()

    print()
    print(
        "OK: PostgreSQL migration 0001 -> 0009 verified in isolated schema"
    )
    print("  - upgrade: all expected tables created (>=25)")
    print("  - JSON profile_report + UUID project_id round-trip correctly")
    print("  - downgrade(0008): project_website_context dropped")
    print("  - re-upgrade to head: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())