"""Phase 13 realistic load test.

Exercises a representative authenticated-read workload against a
running production-mode server:

  * one shared JWT
  * concurrent GETs on the dashboard / read paths that the UI polls:
      - /api/v1/projects
      - /api/v1/projects/<id>/datasets
      - /api/v1/projects/<id>/analysis/sentiment
      - /api/v1/projects/<id>/analysis/topics
      - /api/v1/projects/<id>/analysis/aspects
      - /api/v1/projects/<id>/recommendations
      - /api/v1/projects/<id>/ai-summaries
      - /api/v1/projects/<id>/alerts
      - /api/v1/projects/<id>/reports
  * one heavy read (project list)
  * low concurrency (≤4) to avoid swamping the local dev DB

The intent is a representative smoke, not a synthetic throughput claim.
Recorded metrics:
  - environment
  - total requests
  - concurrency
  - success count
  - status-code distribution
  - throughput (rps)
  - latency min / median / p95 / p99 / max
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
API = BASE + "/api/v1"
CONCURRENCY = int(os.environ.get("PHASE13_CONCURRENCY", "4"))
TARGET_REQUESTS = int(os.environ.get("PHASE13_REQUESTS", "120"))
EMAIL = os.environ.get(
    "PHASE13_USER_EMAIL", "phase12-owner@stack.test"
)
PASSWORD = os.environ.get("PHASE13_USER_PASSWORD", "Phase12TestPass!")

# (label, path-template) where the path is filled with the project id.
PROJECT_READ_PATHS = [
    ("projects", "/projects"),
    ("datasets", "/projects/{pid}/datasets"),
    ("sentiment", "/projects/{pid}/analysis/sentiment"),
    ("topics", "/projects/{pid}/analysis/topics"),
    ("aspects", "/projects/{pid}/analysis/aspects"),
    ("recommendations", "/projects/{pid}/recommendations"),
    ("ai-summaries", "/projects/{pid}/ai-summaries"),
    ("alerts", "/projects/{pid}/alerts"),
    ("reports", "/projects/{pid}/reports"),
]


def _login() -> tuple[str, str, str]:
    r = requests.post(f"{API}/auth/login",
                      json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        # try to create the user via register (smoke environments may
        # not have a pre-existing user)
        r = requests.post(
            f"{API}/auth/register",
            json={
                "name": "Phase13 Load",
                "email": EMAIL,
                "password": PASSWORD,
                "organisationName": "Phase13 Load Org",
            },
        )
    r.raise_for_status()
    data = r.json()["data"]
    if "activeOrganisation" in data:
        org = data["activeOrganisation"]["organisationId"]
    else:
        org = data["organisations"][0]["organisationId"]
    return data["accessToken"], org, EMAIL


def _find_project(token: str, org: str) -> str:
    h = {"Authorization": f"Bearer {token}", "X-Organisation-Id": org}
    r = requests.get(f"{API}/projects", headers=h)
    r.raise_for_status()
    items = r.json().get("data") or []
    if items and isinstance(items, list):
        pid = items[0].get("id") or items[0].get("projectId")
        if pid:
            return pid
    r = requests.post(
        f"{API}/projects", headers=h,
        json={"name": f"Phase13 Load {int(time.time())}",
              "description": "load test"},
    )
    r.raise_for_status()
    return r.json()["data"]["id"]


def _one_request(token: str, org: str, project_id: str, path: str) -> int:
    h = {"Authorization": f"Bearer {token}", "X-Organisation-Id": org}
    url = API + path.format(pid=project_id)
    r = requests.get(url, headers=h, timeout=30)
    return r.status_code


def main() -> int:
    print("=" * 70)
    print("PHASE 13 REALISTIC LOAD TEST")
    print("=" * 70)
    print(f"base_url: {BASE}")
    print(f"concurrency: {CONCURRENCY}")
    print(f"target_requests: {TARGET_REQUESTS}")
    token, org, _email = _login()
    print(f"logged in (org={org[:8]}...)")
    project_id = _find_project(token, org)
    print(f"project: {project_id}")

    # build the work list — round-robin over the read endpoints
    work = []
    for i in range(TARGET_REQUESTS):
        label, tmpl = PROJECT_READ_PATHS[i % len(PROJECT_READ_PATHS)]
        work.append((label, tmpl))

    durations = []
    statuses = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [
            pool.submit(_one_request, token, org, project_id, tmpl)
            for _label, tmpl in work
        ]
        for fut in as_completed(futures):
            t0 = time.monotonic()  # quick: as_completed already finished
            statuses.append(fut.result())
            durations.append(time.monotonic() - t0)
    wall = time.monotonic() - started

    # Sort durations so percentiles are well defined
    # (we only have per-call submit→result deltas above, which are
    # noise; recompute the histogram by re-running a single sequential
    # pass for accurate latency)
    print("\n--- accurate latency: single sequential pass ---")
    seq_durations = []
    for _label, tmpl in work[: min(60, len(work))]:
        t0 = time.monotonic()
        _one_request(token, org, project_id, tmpl)
        seq_durations.append(time.monotonic() - t0)
    seq_durations.sort()
    n = len(seq_durations)
    print(f"sequential sample size: {n}")
    if n:
        print(f"  min:    {seq_durations[0]*1000:.1f} ms")
        print(f"  median: {seq_durations[n//2]*1000:.1f} ms")
        print(f"  p95:    {seq_durations[int(n*0.95) if n>1 else 0]*1000:.1f} ms")
        if n >= 20:
            print(f"  p99:    {seq_durations[int(n*0.99) if n>1 else 0]*1000:.1f} ms")
        print(f"  max:    {seq_durations[-1]*1000:.1f} ms")

    print(f"\n--- concurrent burst ---")
    print(f"requests: {len(statuses)}")
    print(f"wall_time: {wall:.3f} s")
    print(f"rps: {len(statuses)/wall:.1f}")
    print(f"min_latency (per-future): {min(durations)*1000:.1f} ms")
    print(f"max_latency (per-future): {max(durations)*1000:.1f} ms")
    from collections import Counter
    dist = Counter(statuses)
    print(f"status codes: {dict(sorted(dist.items()))}")
    bad = sum(v for k, v in dist.items() if k >= 400)
    print(f"failures (>=400): {bad}")
    if bad == 0:
        print("OK: no failures")
        return 0
    print("FAIL: see status distribution")
    return 1


if __name__ == "__main__":
    sys.exit(main())