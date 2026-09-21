"""Concurrent smoke test for Phase 11 production hardening.

Boots the Flask app in production mode against the existing development
SQLite database (a SQLite DB is acceptable for this microbenchmark — the
goal is to verify the WSGI server handles concurrent requests, not to
benchmark the database).

  python -m scripts.smoke_concurrency
"""
from __future__ import annotations

import os
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def _hit(url: str) -> tuple[float, int]:
    started = time.monotonic()
    with urllib.request.urlopen(url, timeout=10) as resp:
        resp.read()
    return time.monotonic() - started, resp.status


def main() -> int:
    base = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5000")
    endpoint = "/api/v1/health"
    requests = int(os.environ.get("SMOKE_REQUESTS", "200"))
    concurrency = int(os.environ.get("SMOKE_CONCURRENCY", "10"))
    url = base + endpoint

    started = time.monotonic()
    durations: list[float] = []
    statuses: list[int] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_hit, url) for _ in range(requests)]
        for fut in as_completed(futures):
            d, s = fut.result()
            durations.append(d)
            statuses.append(s)
    wall = time.monotonic() - started

    print(f"base_url: {base}")
    print(f"endpoint: {endpoint}")
    print(f"requests: {requests}")
    print(f"concurrency: {concurrency}")
    print(f"wall_time: {wall:.3f}s")
    print(f"rps: {requests / wall:.1f}")
    print(f"min_latency: {min(durations)*1000:.1f}ms")
    print(f"median_latency: {statistics.median(durations)*1000:.1f}ms")
    print(f"p95_latency: {sorted(durations)[int(len(durations)*0.95)]*1000:.1f}ms")
    print(f"max_latency: {max(durations)*1000:.1f}ms")
    bad = sum(1 for s in statuses if s != 200)
    print(f"non_200: {bad}")
    if bad:
        print("FAIL: some requests returned non-200")
        return 1
    print("OK: all requests returned 200")
    return 0


if __name__ == "__main__":
    sys.exit(main())