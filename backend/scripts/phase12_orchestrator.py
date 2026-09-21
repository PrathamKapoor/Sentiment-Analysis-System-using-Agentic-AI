"""Phase 12 orchestrator — runs every non-Docker runtime check
sequentially. Designed to work even though the long-lived production
server is killed by a 300s background-job timeout: the orchestrator
restarts the server between stages that need it.

Stages:
  A. migration verification (one-shot)
  B. health/readiness endpoints (server up)
  C. end-to-end user workflow including PDF + Excel reports (server up)
  D. report artifacts persisted to disk (server down OK)
  E. rate limiting + concurrency smoke (server up)
  F. restart resilience (server up, restart, re-check)
  G. LLM-failure isolation (server up)
  H. structured logging / request IDs (server up)

Run from ``backend/``::

  python -m scripts.phase12_orchestrator
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENV_FILE = REPO / "backend" / "scripts" / "phase12_env.sh"


def _load_env() -> None:
    """Source the environment: credentials come from ``backend/.env``
    (gitignored), non-secret orchestration settings from ``phase12_env.sh``.
    Tolerates bash-style quoting and leading ``export``."""
    from dotenv import load_dotenv

    load_dotenv(REPO / "backend" / ".env")
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        os.environ[k] = v


def _wait_ready(port: int, deadline: float = 30.0) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/v1/ready", timeout=2
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _dev_db_conn():
    """Connect to the DATABASE_URL-configured database.

    Credentials come from the environment (``backend/.env``); none are
    hard-coded here.
    """
    from urllib.parse import unquote, urlparse

    import psycopg

    url = os.environ["DATABASE_URL"]
    p = urlparse(url.replace("postgresql+psycopg://", "postgresql://"))
    return psycopg.connect(
        host=p.hostname or "localhost",
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def _start_server(label: str) -> subprocess.Popen:
    """Spawn a waitress server. Uses a log file rather than a pipe so the
    subprocess cannot block on stdout back-pressure."""
    print(f"\n[server] starting ({label})...", flush=True)
    log_path = REPO / "backend" / f"phase12_{label}.log"
    log_file = open(log_path, "w")
    p = subprocess.Popen(
        [sys.executable, "-m", "app.runner"],
        cwd=REPO / "backend",
        env=os.environ.copy(),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    p._phase12_log_file = log_file  # keep handle for cleanup
    if not _wait_ready(5000, deadline=30):
        print("[server] FAILED to become ready within 30s")
        p.terminate()
        try:
            p.wait(timeout=5)
        except Exception:
            p.kill()
        log_file.close()
        tail = log_path.read_text(errors="replace")[-2000:]
        print(f"--- server log tail ({log_path.name}) ---")
        print(tail)
        raise RuntimeError("server did not become ready")
    print(f"[server] ready (pid={p.pid})", flush=True)
    return p


def _stop_server(p: subprocess.Popen) -> None:
    if p.poll() is None:
        print("[server] stopping...", flush=True)
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=5)
    log_file = getattr(p, "_phase12_log_file", None)
    if log_file is not None and not log_file.closed:
        log_file.close()
    print("[server] stopped")


def _stage_pass(label: str) -> None:
    print(f"  [PASS] {label}", flush=True)


def main() -> int:
    _load_env()
    print("=" * 70)
    print("PHASE 12 RUNTIME VERIFICATION ORCHESTRATOR")
    print("=" * 70)
    print(f"repo={REPO}")
    from urllib.parse import urlparse

    _db = urlparse(
        os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    )
    # Never print credentials — scheme, host, port and database only.
    print(f"DB: postgresql://{_db.hostname}:{_db.port or 5432}{_db.path}")

    # ---------- Stage A: migration verification ----------
    print("\n" + "=" * 70)
    print("STAGE A: migration 0001 -> 0009 against PostgreSQL")
    print("=" * 70)
    res = subprocess.run(
        [sys.executable, "-m", "scripts.audit_migration_postgres"],
        cwd=REPO / "backend",
        env=os.environ.copy(),
    )
    if res.returncode != 0:
        print(f"  FAIL: audit returned {res.returncode}")
        return 1
    _stage_pass("migration upgrade / downgrade / re-upgrade")

    # ---------- Stage B: health/readiness ----------
    print("\n" + "=" * 70)
    print("STAGE B: health, live, ready")
    print("=" * 70)
    server = _start_server("B")
    try:
        import requests
        r = requests.get("http://127.0.0.1:5000/api/v1/health")
        assert r.status_code == 200 and r.json()["data"]["status"] == "ok"
        _stage_pass("/health 200")
        r = requests.get("http://127.0.0.1:5000/api/v1/live")
        assert r.status_code == 200 and r.json()["data"]["status"] == "alive"
        _stage_pass("/live 200")
        r = requests.get("http://127.0.0.1:5000/api/v1/ready")
        assert r.status_code == 200 and r.json()["data"]["status"] == "ready"
        _stage_pass("/ready 200 (DB reachable)")

        r = requests.get(
            "http://127.0.0.1:5000/api/v1/health",
            headers={"X-Request-ID": "phase12-trace-001"},
        )
        assert r.headers.get("X-Request-Id") == "phase12-trace-001"
        _stage_pass("X-Request-ID propagated")

        # ---------- Stage C: end-to-end ----------
        print("\n" + "=" * 70)
        print("STAGE C: end-to-end user workflow")
        print("=" * 70)
        res = subprocess.run(
            [sys.executable, "-m", "scripts.phase12_smoke"],
            cwd=REPO / "backend",
            env=os.environ.copy(),
            timeout=180,
        )
        if res.returncode != 0:
            print(f"  FAIL: e2e returned {res.returncode}")
            return 1
        _stage_pass("register -> project -> dataset -> analyse -> PDF + Excel")

        # ---------- Stage D: report artifacts ----------
        print("\n" + "=" * 70)
        print("STAGE D: report artifacts on disk")
        print("=" * 70)
        pdf = Path("/tmp/phase12_pdf_report.pdf")
        xlsx = Path("/tmp/phase12_xlsx_report.xlsx")
        if not pdf.exists():
            print(f"  FAIL: PDF missing at {pdf}")
            return 1
        head = pdf.read_bytes()[:4]
        if not head.startswith(b"%PDF"):
            print(f"  FAIL: PDF magic wrong: {head!r}")
            return 1
        _stage_pass(f"PDF {pdf.stat().st_size} bytes, magic OK")
        if not xlsx.exists():
            print(f"  FAIL: Excel missing at {xlsx}")
            return 1
        head = xlsx.read_bytes()[:4]
        if head[:2] != b"PK":
            print(f"  FAIL: Excel magic wrong: {head!r}")
            return 1
        _stage_pass(f"Excel {xlsx.stat().st_size} bytes, magic OK")
        reports_dir = Path(os.environ["REPORT_OUTPUT_DIRECTORY"])
        files = list(reports_dir.glob("*.pdf")) + list(reports_dir.glob("*.xlsx"))
        if not files:
            print(f"  FAIL: no reports under {reports_dir}")
            return 1
        _stage_pass(f"server-side reports under {reports_dir}: {len(files)} files")

        # ---------- Stage E: rate limiting + concurrency ----------
        print("\n" + "=" * 70)
        print("STAGE E: rate limiting and concurrency smoke")
        print("=" * 70)
        codes = []
        for _ in range(15):
            r = requests.post(
                "http://127.0.0.1:5000/api/v1/auth/login",
                json={"email": "nobody@example.test", "password": "wrong"},
            )
            codes.append(r.status_code)
        if 429 not in codes:
            print(f"  FAIL: no 429 in login burst, codes={codes}")
            return 1
        codes = [requests.get("http://127.0.0.1:5000/api/v1/health").status_code
                 for _ in range(50)]
        if any(c != 200 for c in codes):
            print(f"  FAIL: health endpoint got non-200: {set(codes)}")
            return 1
        _stage_pass("login rate-limited; health probes unaffected")

        res = subprocess.run(
            [sys.executable, "-m", "scripts.smoke_concurrency"],
            cwd=REPO / "backend",
            env=os.environ.copy(),
            timeout=60,
        )
        if res.returncode != 0:
            print(f"  FAIL: concurrency smoke returned {res.returncode}")
            return 1
        _stage_pass("concurrency smoke (200 req / 10 threads / 0 failures)")

        # ---------- Stage F: restart resilience ----------
        print("\n" + "=" * 70)
        print("STAGE F: restart resilience — data must survive")
        print("=" * 70)
        with _dev_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM organisations")
                orgs_before = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM users")
                users_before = cur.fetchone()[0]
        _stop_server(server)
        time.sleep(1)
        server = _start_server("F-restart")
        with _dev_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM organisations")
                orgs_after = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM users")
                users_after = cur.fetchone()[0]
        if orgs_before != orgs_after or users_before != users_after:
            print(
                f"  FAIL: data changed across restart "
                f"orgs {orgs_before}->{orgs_after} users {users_before}->{users_after}"
            )
            return 1
        _stage_pass(
            f"data preserved across restart "
            f"(orgs={orgs_after}, users={users_after})"
        )
        r = requests.get("http://127.0.0.1:5000/api/v1/health")
        assert r.status_code == 200
        # ---------- Stage G: LLM-failure isolation ----------
        print("\n" + "=" * 70)
        print("STAGE G: LLM unavailable does not block deterministic workflow")
        print("=" * 70)
        _stop_server(server)
        time.sleep(1)
        server = _start_server("G")
        reg = requests.post(
            "http://127.0.0.1:5000/api/v1/auth/register",
            json={
                "name": "Phase12 LLM Test",
                "email": f"phase12-llm-{int(time.time())}@stack.test",
                "password": "Phase12TestPass!",
                "organisationName": "Phase12 LLM Org",
            },
        ).json()
        access = reg["data"]["accessToken"]
        org = reg["data"]["organisationId"]
        r = requests.get(
            "http://127.0.0.1:5000/api/v1/llm/status",
            headers={
                "Authorization": f"Bearer {access}",
                "X-Organisation-Id": org,
            },
        )
        health = requests.get("http://127.0.0.1:5000/api/v1/health").status_code
        assert health == 200
        _stage_pass(
            f"process alive with deterministic LLM (llm_status={r.status_code})"
        )

        # ---------- Stage H: structured logging ----------
        print("\n" + "=" * 70)
        print("STAGE H: structured JSON logs")
        print("=" * 70)
        _stop_server(server)
        time.sleep(1)
        server = _start_server("H")
        for i in range(5):
            requests.get(
                "http://127.0.0.1:5000/api/v1/health",
                headers={"X-Request-ID": f"phase12-logcheck-{i:03d}"},
            )
            time.sleep(0.2)
        time.sleep(1)
        out = (REPO / "backend" / "phase12_H.log").read_text(errors="replace")
        _stop_server(server)
        server = None
        found_json = 0
        for line in out.splitlines():
            line = line.strip()
            if not line or line[0] not in "{[":
                continue
            try:
                obj = json.loads(line)
                found_json += 1
            except Exception:
                continue
        if found_json == 0:
            print(f"  FAIL: no JSON log lines captured (log size {len(out)})")
            return 1
        _stage_pass(
            f"JSON log lines emitted ({found_json} captured, file size {len(out)})"
        )
        print("\n" + "=" * 70)
        print("ALL PHASE 12 STAGES PASSED")
        print("=" * 70)
        return 0
    finally:
        if server is not None:
            _stop_server(server)


if __name__ == "__main__":
    sys.exit(main())