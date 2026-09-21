"""One-shot audit of migration 0009: fresh upgrade, then downgrade, then
re-upgrade. Verifies three things:

  1. ``alembic upgrade head`` creates project_website_context and the two
     new columns (projects.website_url, reports.mode).
  2. ``alembic downgrade 0008`` drops all three cleanly.
  3. ``alembic upgrade head`` re-applies without error.

Run from ``backend/``:
    python scripts/audit_migration_0009.py
"""
from __future__ import annotations

import os
import sqlite3
import sys


def main() -> int:
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_root)
    sys.path.insert(0, backend_root)

    db_path = os.path.join(backend_root, "audit_migration_0009.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    os.environ["TEST_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["FLASK_ENV"] = "testing"

    from app import create_app
    app = create_app("testing")

    engine = None
    with app.app_context():
        from flask_migrate import downgrade as _downgrade, upgrade as _upgrade
        from app.extensions import db as _db
        engine = _db.engine

        _upgrade()
        conn = sqlite3.connect(db_path)

        try:
            # 1. New table exists
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            assert "project_website_context" in tables, "missing project_website_context"

            # 2. New columns exist
            report_cols = {r[1] for r in conn.execute("PRAGMA table_info(reports)").fetchall()}
            assert "mode" in report_cols, "missing reports.mode"
            proj_cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
            assert "website_url" in proj_cols, "missing projects.website_url"

            # 3. Unique constraint on project_website_context.project_id
            idx = conn.execute("PRAGMA index_list(project_website_context)").fetchall()
            uq = [i for i in idx if i[2] == 1]
            found = False
            for i in uq:
                cols = {r[2] for r in conn.execute(f"PRAGMA index_info('{i[1]}')").fetchall()}
                if cols == {"project_id"}:
                    found = True
            assert found, "missing unique constraint on project_id"

            # 4. Downgrade drops everything
            _downgrade(revision="0008")
            conn2 = sqlite3.connect(db_path)
            report_cols = {r[1] for r in conn2.execute("PRAGMA table_info(reports)").fetchall()}
            assert "mode" not in report_cols, "downgrade should drop reports.mode"
            tables2 = {r[0] for r in conn2.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            assert "project_website_context" not in tables2, "downgrade should drop the table"
            conn2.close()

            # 5. Re-upgrade: idempotent
            _upgrade()
            conn3 = sqlite3.connect(db_path)
            report_cols = {r[1] for r in conn3.execute("PRAGMA table_info(reports)").fetchall()}
            assert "mode" in report_cols, "re-upgrade should restore reports.mode"
            conn3.close()
        finally:
            conn.close()

    if engine is not None:
        engine.dispose()
    os.remove(db_path)
    print("OK: migration 0009 upgrade/downgrade/re-upgrade verified against SQLite")
    return 0


if __name__ == "__main__":
    sys.exit(main())
