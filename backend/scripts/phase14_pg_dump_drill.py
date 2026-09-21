"""Phase 14 — REAL operator backup/restore drill using pg_dump + pg_restore.

This complements (does not replace) the Phase 13 Python-level drill.
It uses the actual operator binaries — ``pg_dump`` (custom format) and
``pg_restore`` — against a fully migrated, populated, isolated schema
inside the configured development database. No production data and no
other database is touched.

Flow:

  1. Locate pg_dump / pg_restore (PATH, then the standard PostgreSQL 18
     install directory).
  2. CREATE SCHEMA p14_drill_src inside the configured DATABASE_URL.
  3. Run the real Alembic chain (0001 -> head) INTO that schema via
     ``flask db upgrade`` with a search_path-pinned URL  — the schema
     under test is therefore a genuine migration product.
  4. Populate every drill table by copying the development data
     (FK-ordered INSERT ... SELECT) so real UUID / JSONB / unicode
     values are under test.
  5. Snapshot every table (count + md5 of ordered row_to_json), the
     FK/index counts, and the alembic_version row.
  6. pg_dump -Fc -n p14_drill_src  -> custom-format backup file.
  7. DROP SCHEMA ... CASCADE (destroy the target).
  8. pg_restore (plain) -> verify the snapshot matches EXACTLY.
  9. Corrupt the result (delete rows, drop a table), then
     pg_restore --clean --if-exists (operator restore-over-existing)
     -> verify the snapshot matches EXACTLY again.
 10. Cleanup: drop the drill schema, delete the backup file.

Usage::

    python -m scripts.phase14_pg_dump_drill

Exit code 0 = the operator backup path (pg_dump/pg_restore) round-trips
the full migrated schema byte-for-byte at the row level.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse, unquote, quote

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = "p14_drill_src"
PG_BIN_FALLBACK = r"C:\Program Files\PostgreSQL\18\bin"


def _find_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    candidate = os.path.join(PG_BIN_FALLBACK, f"{name}.exe")
    if os.path.isfile(candidate):
        return candidate
    raise SystemExit(f"{name} not found on PATH or in {PG_BIN_FALLBACK}")


def _parse_database_url(url: str) -> dict:
    # postgresql+psycopg://user:pass@host:port/dbname
    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://"))
    if parsed.scheme != "postgresql":
        raise SystemExit("DATABASE_URL must be PostgreSQL for this drill")
    return {
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/"),
    }


def _connect(db: dict):
    import psycopg

    return psycopg.connect(
        host=db["host"],
        port=db["port"],
        user=db["user"],
        password=db["password"],
        dbname=db["dbname"],
        autocommit=True,
        connect_timeout=5,
    )


def _run_migrations(db: dict) -> None:
    env = os.environ.copy()
    # The password may contain URL-hostile characters (@, :, /) that
    # were percent-encoded in the original DATABASE_URL. Re-encode so
    # libpq does not split the authority at the wrong '@'.
    url = (
        f"postgresql+psycopg://{quote(db['user'], safe='')}"
        f":{quote(db['password'], safe='')}"
        f"@{db['host']}:{db['port']}/{db['dbname']}"
        f"?options=-csearch_path%3D{SCHEMA}"
    )
    env["DATABASE_URL"] = url
    env["FLASK_APP"] = "run.py"
    res = subprocess.run(
        [sys.executable, "-m", "flask", "db", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if res.returncode != 0:
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        raise SystemExit("flask db upgrade into drill schema failed")


def _tables(conn, schema: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY 1",
            (schema,),
        )
        return [r[0] for r in cur.fetchall()]


def _topo_order(conn, tables: list[str]) -> list[str]:
    """Order ``tables`` so every table is inserted after the tables its
    foreign keys reference. Self-references are ignored (INSERT ...
    SELECT of the full set sees its own rows)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT kcu.table_name AS child,
                   ccu.table_name  AS parent
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema    = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
             AND tc.table_schema    = ccu.constraint_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
            """
        )
        edges = [(c, p) for c, p in cur.fetchall() if c != p]

    members = set(tables) - {"alembic_version"}
    deps: dict[str, set[str]] = {t: set() for t in members}
    for child, parent in edges:
        if child in members and parent in members:
            deps[child].add(parent)

    ordered: list[str] = []
    remaining = dict(deps)
    while remaining:
        ready = sorted(t for t, d in remaining.items() if not (d - set(ordered)))
        if not ready:
            raise SystemExit(f"FK cycle cannot be ordered: {sorted(remaining)}")
        for t in ready:
            ordered.append(t)
            remaining.pop(t)
    return ordered


def _identity_always_tables(conn, tables: list[str]) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT table_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ANY(%s)
              AND is_identity = 'YES'
              AND identity_generation = 'ALWAYS'
            """,
            (tables,),
        )
        return {r[0] for r in cur.fetchall()}


def _populate(conn) -> None:
    public = set(_tables(conn, "public"))
    drill = set(_tables(conn, SCHEMA))
    common = sorted((public & drill) - {"alembic_version"})
    order = _topo_order(conn, common)
    always = _identity_always_tables(conn, common)
    with conn.cursor() as cur:
        for table in order:
            overriding = (
                " OVERRIDING SYSTEM VALUE" if table in always else ""
            )
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{table}"{overriding} '
                f'SELECT * FROM "public"."{table}"'
            )
    return order


def _snapshot(conn) -> dict:
    snap: dict[str, tuple[int, str]] = {}
    with conn.cursor() as cur:
        for table in _tables(conn, SCHEMA):
            cur.execute(
                f'SELECT count(*), coalesce(md5(string_agg(j, '
                f"E'\\n' ORDER BY j)), 'empty') "
                f'FROM (SELECT row_to_json(t)::text AS j '
                f'FROM "{SCHEMA}"."{table}" t) s'
            )
            count, digest = cur.fetchone()
            snap[table] = (count, digest)
        cur.execute(
            "SELECT count(*) FROM information_schema.table_constraints "
            "WHERE table_schema=%s AND constraint_type='FOREIGN KEY'",
            (SCHEMA,),
        )
        snap["<fk_count>"] = (cur.fetchone()[0], "")
        cur.execute(
            "SELECT count(*) FROM pg_indexes WHERE schemaname=%s",
            (SCHEMA,),
        )
        snap["<index_count>"] = (cur.fetchone()[0], "")
        cur.execute(f'SELECT version_num FROM "{SCHEMA}"."alembic_version"')
        row = cur.fetchone()
        snap["<alembic_version>"] = (0, row[0] if row else "MISSING")
    return snap


def _compare(before: dict, after: dict, label: str) -> list[str]:
    failures = []
    keys = set(before) | set(after)
    for key in sorted(keys):
        if before.get(key) != after.get(key):
            failures.append(f"{label}: mismatch on {key}: {before.get(key)} != {after.get(key)}")
    return failures


def _pg_env(db: dict) -> dict:
    env = os.environ.copy()
    env["PGPASSWORD"] = db["password"]
    return env


def _pg_dump(db: dict, dump_file: str) -> None:
    tool = _find_tool("pg_dump")
    cmd = [
        tool, "-U", db["user"], "-h", db["host"], "-p", str(db["port"]),
        "-F", "c", "-n", SCHEMA, "-f", dump_file, db["dbname"],
    ]
    res = subprocess.run(cmd, env=_pg_env(db), capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        raise SystemExit(f"pg_dump failed:\n{res.stderr}")
    size = os.path.getsize(dump_file)
    print(f"[P14-DRILL] pg_dump -> {dump_file} ({size} bytes, custom format)")


def _pg_restore(db: dict, dump_file: str, clean: bool) -> None:
    tool = _find_tool("pg_restore")
    cmd = [
        tool, "-U", db["user"], "-h", db["host"], "-p", str(db["port"]),
        "-d", db["dbname"],
    ]
    if clean:
        cmd += ["--clean", "--if-exists"]
    cmd.append(dump_file)
    res = subprocess.run(cmd, env=_pg_env(db), capture_output=True, text=True, timeout=300)
    # pg_restore emits notices on stderr even on success; only a
    # non-zero exit code is a failure.
    if res.returncode != 0:
        raise SystemExit(f"pg_restore failed:\n{res.stderr}")


def main() -> int:
    print("=" * 72)
    print("PHASE 14 — REAL OPERATOR pg_dump / pg_restore DRILL")
    print("=" * 72)

    from dotenv import load_dotenv

    load_dotenv(os.path.join(BACKEND_DIR, ".env"))
    url = os.environ.get("DATABASE_URL", "")
    db = _parse_database_url(url)
    print(f"[P14-DRILL] target: {db['user']}@{db['host']}:{db['port']}/{db['dbname']}")
    print(f"[P14-DRILL] pg_dump:    {_find_tool('pg_dump')}")
    print(f"[P14-DRILL] pg_restore: {_find_tool('pg_restore')}")

    dump_file = os.path.join(tempfile.gettempdir(), "p14_drill.backup")
    if os.path.exists(dump_file):
        os.remove(dump_file)

    conn = _connect(db)
    failures: list[str] = []
    try:
        # --- 1 + 2: build the isolated, fully migrated schema ----------
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
            cur.execute(f'CREATE SCHEMA "{SCHEMA}"')
        print(f"[P14-DRILL] created isolated schema {SCHEMA}")

        _run_migrations(db)
        n_tables = len(_tables(conn, SCHEMA))
        print(f"[P14-DRILL] migrations 0001->head complete: {n_tables} tables")
        if n_tables < 25:
            failures.append(f"expected >=25 tables after migration, got {n_tables}")

        # --- 4: populate from the dev data (FK-ordered) ---------------
        order = _populate(conn)
        print(f"[P14-DRILL] populated {len(order)} tables (FK-ordered copy)")

        snap_before = _snapshot(conn)
        populated = {t: c for t, (c, _) in snap_before.items()
                     if not t.startswith("<") and c > 0}
        print(f"[P14-DRILL] tables with data: {len(populated)}")
        for t, c in sorted(populated.items()):
            print(f"    {t:32s} {c:5d} rows")
        print(f"[P14-DRILL] FK constraints: {snap_before['<fk_count>'][0]}, "
              f"indexes: {snap_before['<index_count>'][0]}, "
              f"alembic head: {snap_before['<alembic_version>'][1]}")

        # --- 6: REAL pg_dump -------------------------------------------
        _pg_dump(db, dump_file)

        # --- 7: destroy the target --------------------------------------
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA "{SCHEMA}" CASCADE')
        print("[P14-DRILL] target schema DESTROYED (DROP SCHEMA CASCADE)")

        # --- 8: REAL pg_restore (fresh restore) + verify ----------------
        _pg_restore(db, dump_file, clean=False)
        snap_restored = _snapshot(conn)
        failures += _compare(snap_before, snap_restored, "restore-1")
        if not _compare(snap_before, snap_restored, "restore-1"):
            print("[P14-DRILL] restore-1 (fresh): snapshot EXACT match")

        # --- 9: corrupt + operator restore --clean --if-exists ----------
        with conn.cursor() as cur:
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."sentiment_results" '
                f"WHERE ctid IN (SELECT ctid FROM \"{SCHEMA}\".\"sentiment_results\" "
                f"LIMIT 5)"
            )
            cur.execute(f'DROP TABLE "{SCHEMA}"."review_topics"')
        print("[P14-DRILL] corruption injected (rows deleted, table dropped)")
        _pg_restore(db, dump_file, clean=True)
        snap_restored2 = _snapshot(conn)
        failures += _compare(snap_before, snap_restored2, "restore-2")
        if not _compare(snap_before, snap_restored2, "restore-2"):
            print("[P14-DRILL] restore-2 (--clean --if-exists): snapshot EXACT match")
    finally:
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
        conn.close()
        if os.path.exists(dump_file):
            os.remove(dump_file)
        print("[P14-DRILL] cleanup complete (schema dropped, dump removed)")

    print()
    print("=" * 72)
    if failures:
        for f in failures:
            print(f"  [FAIL] {f}")
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS — pg_dump/pg_restore round-trip verified byte-exact "
          "at row level (counts, md5, FKs, indexes, alembic head).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
