"""Phase 14 — distributed (multi-instance) runtime verification.

Boots TWO real backend processes (waitress, production config) against:

  * one real PostgreSQL database (the configured dev database), and
  * one real Redis server (localhost), using dedicated logical DBs:

      - DB 5  -> REVOCATION_STORE_URL (JWT revocation)
      - DB 6  -> LIMITER_STORAGE_URL (rate limiting)

and proves, over real HTTP, that security state is SHARED:

  Stage 1  Token minted on A is accepted on B; logout on A revokes it;
           the SAME token is then rejected on B.        (multi-instance
           JWT revocation — the Phase 14 headline gap)
  Stage 2  Refresh-token rotation on B; replaying the old refresh
           token is rejected on BOTH instances.
  Stage 3  A revoked token stays revoked after ALL processes are
           killed and a brand-new process C boots (restart persistence
           through Redis).
  Stage 4  The 10-per-minute login budget is ONE shared budget across
           A and B (not 10 per instance): after 10 accepted attempts
           split across both processes, the 11th is 429 on both.

Safety:

  * Only Redis logical DBs 5 and 6 are flushed — never DB 0.
  * Child processes bind 127.0.0.1 only and are always terminated.
  * Register/login calls create uniquely-namespaced synthetic rows in
    the configured (development) database.

Prerequisites: Redis running on localhost:6379; backend/.env (or the
process env) providing DATABASE_URL. Exit code 0 = all stages passed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import uuid

import requests

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PORT_A, PORT_B, PORT_C = 5181, 5182, 5183
REDIS_REVOCATION_URL = "redis://localhost:6379/5"
REDIS_LIMITER_URL = "redis://localhost:6379/6"

RESULTS: list[tuple[str, bool, str]] = []


def record(stage: str, ok: bool, detail: str) -> None:
    RESULTS.append((stage, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[P14][{mark}] {stage}: {detail}")


def _load_env() -> dict:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(BACKEND_DIR, ".env"))
    env = os.environ.copy()
    if not env.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required (backend/.env)")
    env.update(
        {
            "FLASK_ENV": "production",
            "SECRET_KEY": "p14-verify-secret-" + uuid.uuid4().hex,
            "JWT_SECRET_KEY": "p14-verify-jwt-" + uuid.uuid4().hex,
            "CORS_ALLOWED_ORIGINS": "http://localhost:5173",
            "TRUSTED_PROXY_COUNT": "0",
            "RATE_LIMIT_ENABLED": "true",
            "LIMITER_STORAGE_URL": REDIS_LIMITER_URL,
            "REVOCATION_STORE_URL": REDIS_REVOCATION_URL,
            "LOG_JSON": "true",
            "LOG_LEVEL": "WARNING",
            "WEB_CONCURRENCY": "2",
            "BIND_ADDRESS": "127.0.0.1",
        }
    )
    return env


def _flush_redis_dbs() -> None:
    import redis

    for url in (REDIS_REVOCATION_URL, REDIS_LIMITER_URL):
        redis.Redis.from_url(url, socket_timeout=3).flushdb()


def _start(port: int, env: dict, tag: str) -> subprocess.Popen:
    child_env = env.copy()
    child_env["PORT"] = str(port)
    log_path = os.path.join(tempfile.gettempdir(), f"p14_instance_{tag}.log")
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.runner"],
        cwd=BACKEND_DIR,
        env=child_env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    proc._sams_log_path = log_path  # type: ignore[attr-defined]
    return proc


def _wait_health(port: int, proc: subprocess.Popen, timeout: float = 60.0) -> None:
    url = f"http://127.0.0.1:{port}/api/v1/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            with open(proc._sams_log_path, encoding="utf-8") as fh:  # type: ignore[attr-defined]
                tail = fh.read()[-3000:]
            raise RuntimeError(
                f"process on :{port} exited early (rc={proc.returncode}):\n{tail}"
            )
        try:
            if requests.get(url, timeout=2).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"instance on :{port} did not become healthy in {timeout}s")


def _wait_for_fresh_minute() -> None:
    """Sleep until we are close to the start of a fresh fixed-window
    minute, so a rate-limit burst sits entirely inside ONE window."""
    while True:
        now = time.time()
        if now % 60 < 4:
            return
        time.sleep(1.0)


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    print("=" * 72)
    print("PHASE 14 — DISTRIBUTED MULTI-INSTANCE VERIFICATION (2 processes + Redis)")
    print("=" * 72)

    env = _load_env()
    _flush_redis_dbs()

    proc_a = proc_b = proc_c = None
    try:
        proc_a = _start(PORT_A, env, "A")
        proc_b = _start(PORT_B, env, "B")
        _wait_health(PORT_A, proc_a)
        _wait_health(PORT_B, proc_b)
        print(f"[P14] instances healthy: A=:{PORT_A} B=:{PORT_B}")

        base_a = f"http://127.0.0.1:{PORT_A}/api/v1"
        base_b = f"http://127.0.0.1:{PORT_B}/api/v1"
        suffix = uuid.uuid4().hex[:12]
        email = f"p14-{suffix}@example.invalid"
        password = "P14-Verify-Str0ng!"

        # ------------------------------------------------ Stage 1
        r = requests.post(
            f"{base_a}/auth/register",
            json={
                "organisationName": f"P14 Verify Org {suffix}",
                "email": email,
                "password": password,
                "name": "P14 Verifier",
            },
            timeout=10,
        )
        ok = r.status_code == 201
        record("stage1.register_on_A", ok, f"HTTP {r.status_code}")
        if not ok:
            raise RuntimeError(f"register failed: {r.status_code} {r.text[:300]}")
        tokens = r.json()["data"]
        access = tokens["accessToken"]
        auth = {"Authorization": f"Bearer {access}"}

        r = requests.get(f"{base_b}/auth/me", headers=auth, timeout=10)
        record(
            "stage1.token_accepted_on_B",
            r.status_code == 200,
            f"HTTP {r.status_code} (token minted on A, used on B)",
        )

        r = requests.post(f"{base_a}/auth/logout", headers=auth, timeout=10)
        record("stage1.logout_on_A", r.status_code == 200, f"HTTP {r.status_code}")

        r = requests.get(f"{base_b}/auth/me", headers=auth, timeout=10)
        record(
            "stage1.revoked_token_rejected_on_B",
            r.status_code == 401,
            f"HTTP {r.status_code} (revoked on A, rejected on B via shared Redis)",
        )

        # ------------------------------------------------ Stage 2
        r = requests.post(
            f"{base_a}/auth/login",
            json={"email": email, "password": password},
            timeout=10,
        )
        record("stage2.login_on_A", r.status_code == 200, f"HTTP {r.status_code}")
        refresh_token = r.json()["data"]["refreshToken"]
        rauth = {"Authorization": f"Bearer {refresh_token}"}

        r = requests.post(f"{base_b}/auth/refresh", headers=rauth, timeout=10)
        record(
            "stage2.refresh_rotation_on_B",
            r.status_code == 200,
            f"HTTP {r.status_code} (refresh token issued by A accepted on B)",
        )

        r = requests.post(f"{base_b}/auth/refresh", headers=rauth, timeout=10)
        replay_b = r.status_code == 401
        r = requests.post(f"{base_a}/auth/refresh", headers=rauth, timeout=10)
        replay_a = r.status_code == 401
        record(
            "stage2.old_refresh_rejected_on_both",
            replay_b and replay_a,
            f"replay on B -> {'401' if replay_b else 'NOT-401'}, "
            f"replay on A -> {'401' if replay_a else 'NOT-401'}",
        )

        # ------------------------------------------------ Stage 3
        r = requests.post(
            f"{base_a}/auth/login",
            json={"email": email, "password": password},
            timeout=10,
        )
        token3 = r.json()["data"]["accessToken"]
        auth3 = {"Authorization": f"Bearer {token3}"}
        requests.post(f"{base_a}/auth/logout", headers=auth3, timeout=10)

        _stop(proc_a)
        proc_a = None
        _stop(proc_b)
        proc_b = None
        print("[P14] both instances stopped; booting fresh instance C...")
        proc_c = _start(PORT_C, env, "C")
        _wait_health(PORT_C, proc_c)

        r = requests.get(
            f"http://127.0.0.1:{PORT_C}/api/v1/auth/me", headers=auth3, timeout=10
        )
        record(
            "stage3.revocation_survives_full_restart",
            r.status_code == 401,
            f"HTTP {r.status_code} on a brand-new process (Redis-persisted)",
        )

        # ------------------------------------------------ Stage 4
        # Budget: 10 logins/min per client IP (all requests here come
        # from 127.0.0.1). Processes A/B are down from Stage 3; fresh
        # process C is up, and we boot a second fresh process B. Five
        # accepted attempts on C + five on B exhaust the SHARED budget
        # — the 11th (on C) and 12th (on B) must both be 429. If the
        # budget were per-process, B alone would still have 5 left.
        #
        # Age out earlier-stage logins first: Flask-Limiter's window
        # strategy may be sliding/elastic, so a plain minute-boundary
        # wait is not sufficient to guarantee an empty bucket. 62s of
        # silence followed by alignment to a fresh minute boundary
        # covers fixed, elastic, and sliding windows alike.
        print("[P14] stage4: waiting 62s so earlier login attempts age out...")
        time.sleep(62)
        _wait_for_fresh_minute()
        base_c = f"http://127.0.0.1:{PORT_C}/api/v1"

        statuses_c: list[int] = []
        for _ in range(5):
            r = requests.post(
                f"{base_c}/auth/login",
                json={"email": "nobody@example.invalid", "password": "wrong"},
                timeout=10,
            )
            statuses_c.append(r.status_code)

        proc_b = _start(PORT_B, env, "B2")
        _wait_health(PORT_B, proc_b)

        statuses_b: list[int] = []
        for _ in range(5):
            r = requests.post(
                f"{base_b}/auth/login",
                json={"email": "nobody@example.invalid", "password": "wrong"},
                timeout=10,
            )
            statuses_b.append(r.status_code)

        # After 5 (C) + 5 (B) accepted attempts = 10, both must be 429.
        r_c = requests.post(
            f"{base_c}/auth/login",
            json={"email": "nobody@example.invalid", "password": "wrong"},
            timeout=10,
        )
        r_b = requests.post(
            f"{base_b}/auth/login",
            json={"email": "nobody@example.invalid", "password": "wrong"},
            timeout=10,
        )
        accepted = [s for s in statuses_c + statuses_b if s == 401]
        ok = (
            len(accepted) == 10
            and r_c.status_code == 429
            and r_b.status_code == 429
        )
        record(
            "stage4.shared_login_budget",
            ok,
            f"accepted(401)={len(accepted)} across C+B, then C->{r_c.status_code}, "
            f"B->{r_b.status_code} (limit is 10/min per client IP, shared)",
        )
    finally:
        for p in (proc_c, proc_b, proc_a):
            _stop(p)
        _flush_redis_dbs()

    print()
    print("=" * 72)
    failed = [s for s, ok, _ in RESULTS if not ok]
    for stage, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {stage} — {detail}")
    print("=" * 72)
    if failed:
        print(f"RESULT: FAIL ({len(failed)} stage(s) failed)")
        return 1
    print("RESULT: PASS — distributed security state verified over HTTP + Redis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
