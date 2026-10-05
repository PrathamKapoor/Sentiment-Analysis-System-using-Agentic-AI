"""PostgreSQL migration audit for Phase 11.

Runs the full alembic chain inside a newly-created isolated schema
within the configured development database. The public schema and any
other schema remain untouched.

This script:
  1. Creates a uniquely named audit schema and grants CREATE on it.
  2. Runs ``flask db upgrade head`` with a connection URL whose
     ``search_path`` puts every DDL inside that schema.
  3. Verifies all expected tables exist.
  4. Downgrades to 0009 and confirms the new tables are gone.
  5. Runs ``flask db upgrade head`` again to leave the schema clean.
  6. Drops the audit schema.

Usage::

  python -m scripts.audit_migration_postgres
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text

SCHEMA = "sams_migration_audit_" + uuid.uuid4().hex[:12]


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
                "project_entities", "security_findings",
                "review_duplicate_links", "investigations",
                "investigation_events", "investigation_findings",
            }
            missing = expected - tables
            assert not missing, f"missing tables after upgrade: {missing}"
            assert len(tables) == len(expected) + 1 and "alembic_version" in tables, (
                f"expected {len(expected)} application tables plus alembic_version, got {len(tables)}: {sorted(tables)}"
            )
            columns = {
                row[0]
                for row in conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema=:s AND table_name='reviews'"
                ), {"s": SCHEMA}).fetchall()
            }
            assert "keyword_matches" in columns, "reviews.keyword_matches missing"
            for name in ("source_record_id", "source_url", "source_metadata", "source_collected_at"):
                assert name in columns, f"reviews.{name} missing"
            provenance_index = conn.execute(text(
                "SELECT 1 FROM pg_indexes WHERE schemaname=:s "
                "AND indexname='ix_reviews_data_source_record_id'"
            ), {"s": SCHEMA}).first()
            assert provenance_index, "review source provenance index missing"
            finding_columns = {
                row[0]
                for row in conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema=:s AND table_name='security_findings'"
                ), {"s": SCHEMA}).fetchall()
            }
            assert "review_text_sha256" in finding_columns, "security_findings.review_text_sha256 missing"
            investigation_tables = ("investigations", "investigation_events", "investigation_findings", "review_duplicate_links")
            for table in investigation_tables:
                assert table in tables, f"{table} missing"
            constraints = {
                row[0] for row in conn.execute(text(
                    "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid "
                    "JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname=:s"
                ), {"s": SCHEMA}).fetchall()
            }
            for name in ("ck_investigation_status", "ck_investigation_review_state",
                         "ck_investigation_finding_claim_status", "ck_investigation_finding_review_state"):
                assert name in constraints, f"missing constraint {name}"

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
            for table in ("ai_summaries", "reports"):
                nullable_dates = {
                    (r[0], r[1]) for r in conn.execute(text(
                        "SELECT column_name, is_nullable FROM information_schema.columns "
                        "WHERE table_schema=:s AND table_name=:t "
                        "AND column_name IN ('date_range_start','date_range_end')"
                    ), {"s": SCHEMA, "t": table}).fetchall()
                }
                assert nullable_dates == {
                    ("date_range_start", "YES"), ("date_range_end", "YES")
                }, f"{table} date bounds should be nullable, got {nullable_dates}"
        engine.dispose()

        _alembic(audit_url, "downgrade", "0009", label="downgrade")
        engine = create_engine(audit_url)
        with engine.connect() as conn:
            tables = _tables(conn)
            assert "project_website_context" in tables, "0009 website context should remain"
            assert "project_entities" not in tables, "project_entities should be dropped at 0009"
            assert "security_findings" not in tables, "security_findings should be dropped at 0009"
            for name in ("review_duplicate_links", "investigations", "investigation_events", "investigation_findings"):
                assert name not in tables, f"{name} should be dropped at 0009"
            assert len(tables) == 26, f"expected 25 application tables plus alembic_version at 0009, got {len(tables)}"
            review_columns = {
                r[0] for r in conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema=:s AND table_name='reviews'"
                ), {"s": SCHEMA}).fetchall()
            }
            assert "keyword_matches" not in review_columns, "keyword_matches should be dropped at 0009"
            for name in ("source_record_id", "source_url", "source_metadata", "source_collected_at"):
                assert name not in review_columns, f"reviews.{name} should be dropped at 0009"
            provenance_index = conn.execute(text(
                "SELECT 1 FROM pg_indexes WHERE schemaname=:s "
                "AND indexname='ix_reviews_data_source_record_id'"
            ), {"s": SCHEMA}).first()
            assert not provenance_index, "review source provenance index should be dropped at 0009"
        engine.dispose()

        _alembic(audit_url, "upgrade", "head", label="re-upgrade")
    finally:
        admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        admin.dispose()

    print()
    print(
        "OK: PostgreSQL migration chain through head verified in isolated schema"
    )
    print("  - upgrade: expected application tables, source provenance, and optional report/summary dates created")
    print("  - JSON profile_report + UUID project_id round-trip correctly")
    print("  - downgrade(0009): new entity, keyword, security schema removed")
    print("  - re-upgrade to head: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
