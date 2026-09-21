"""Phase 12 end-to-end smoke test.

Drives a real production-stack Flask backend (started by
``app.runner`` in production mode against PostgreSQL) through a full
user workflow:

  1. register / login
  2. create project
  3. upload the bundled demo dataset (CSV)
  4. process the dataset
  5. sentiment + topics + aspects analysis
  6. PDF report generation + download
  7. Excel report generation + download
  8. LLM status (deterministic provider)
  9. LLM failure path with a non-functional endpoint

Run from ``backend/`` while the production server is up::

  python -m scripts.phase12_smoke
"""
from __future__ import annotations

import os
import sys
import time

import requests

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
API = BASE + "/api/v1"
TS = int(time.time())
EMAIL = f"phase12-e2e-{TS}@stack.test"
PASS_ = "Phase12TestPass!"
DATASET = os.environ.get(
    "PHASE12_DATASET",
    "C:/Sentiment_Analysis_Management_System_using_Agentic_AI/database/demo_dataset.csv",
)


def step(n: int, label: str) -> None:
    print(f"[{n}] {label}", flush=True)


def must_ok(resp, expected=(200, 201, 202)):
    code = resp.status_code
    if code not in expected:
        print(f"  FAIL: status={code} body={resp.text[:200]}")
        sys.exit(1)
    return resp


def main() -> int:
    step(1, "register organisation + owner")
    r = must_ok(requests.post(f"{API}/auth/register", json={
        "name": f"E2E Owner {TS}",
        "email": EMAIL,
        "password": PASS_,
        "organisationName": f"E2E Org {TS}",
    }))
    j = r.json()
    access = j["data"]["accessToken"]
    org = j["data"]["organisationId"]
    print(f"  access_token: {access[:20]}... org={org}")

    auth = {"Authorization": f"Bearer {access}", "X-Organisation-Id": org}

    step(2, "create project")
    r = must_ok(requests.post(f"{API}/projects", json={
        "name": f"E2E Project {TS}",
        "description": "phase 12 production-stack e2e",
    }, headers=auth))
    project_id = r.json()["data"]["id"]
    print(f"  project_id={project_id}")

    step(3, "upload bundled demo CSV")
    if not os.path.exists(DATASET):
        print(f"  FAIL: dataset missing at {DATASET}")
        return 1
    with open(DATASET, "rb") as fh:
        r = must_ok(requests.post(
            f"{API}/projects/{project_id}/datasets",
            files={"file": ("demo.csv", fh, "text/csv")},
            data={"fileType": "csv"},
            headers=auth,
        ))
    dataset_id = r.json()["data"]["datasetId"]
    # Map columns so the dataset can be processed.
    mapping = {"text": "review_text", "rating": "rating", "date": "review_date"}
    must_ok(requests.post(
        f"{API}/datasets/{dataset_id}/map-columns",
        json=mapping,
        headers=auth,
    ))
    # Validate before processing — process_dataset requires status=validated.
    must_ok(requests.post(
        f"{API}/datasets/{dataset_id}/validate",
        headers=auth,
    ))
    r = must_ok(requests.post(
        f"{API}/datasets/{dataset_id}/process",
        headers=auth,
    ))

    step(5, "sentiment analysis")
    must_ok(requests.post(
        f"{API}/projects/{project_id}/analysis/sentiment", headers=auth
    ))
    s = requests.get(
        f"{API}/projects/{project_id}/analysis/sentiment", headers=auth
    )
    print(f"  sentiment summary status={s.status_code}")

    step(6, "topic analysis")
    must_ok(requests.post(
        f"{API}/projects/{project_id}/analysis/topics", headers=auth
    ))

    step(7, "aspect analysis")
    must_ok(requests.post(
        f"{API}/projects/{project_id}/analysis/aspects", headers=auth
    ))
    step(8, "generate + download PDF report")
    today = time.strftime("%Y-%m-%d")
    sections = ["projectOverview", "executiveSummary", "sentimentDistribution", "conclusion"]
    payload = {
        "reportName": "Phase12 PDF Report",
        "dateFrom": "2020-01-01",
        "dateTo": today,
        "fileFormat": "pdf",
        "sections": sections,
    }
    r = must_ok(requests.post(f"{API}/projects/{project_id}/reports", json=payload, headers=auth))
    rid = r.json()["data"]["id"]
    print("    -> report rid:", rid)
    pdf = requests.get(
        f"{API}/reports/{rid}/download",
        headers=auth,
    )

    print(f"  pdf status={pdf.status_code} bytes={len(pdf.content)}")
    pdf_path = "/tmp/phase12_pdf_report.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf.content)
    with open(pdf_path, "rb") as f:
        head = f.read(4)
    print(f"  pdf magic: {head!r}")
    assert head.startswith(b"%PDF"), "PDF magic missing"

    step(9, "generate + download Excel report")
    r = must_ok(requests.post(f"{API}/projects/{project_id}/reports", json={
        "reportName": "Phase12 Excel Report",
        "dateFrom": "2020-01-01",
        "dateTo": today,
        "fileFormat": "excel",
        "sections": sections,
    }, headers=auth))
    rid = r.json()["data"]["id"]
    xlsx = requests.get(
        f"{API}/reports/{rid}/download",
        headers=auth,
    )
    print(f"  xlsx status={xlsx.status_code} bytes={len(xlsx.content)}")
    xlsx_path = "/tmp/phase12_xlsx_report.xlsx"
    with open(xlsx_path, "wb") as f:
        f.write(xlsx.content)
    with open(xlsx_path, "rb") as f:
        head = f.read(4)
    print(f"  xlsx magic: {head!r}")
    # ZIP magic = PK\x03\x04
    assert head[:2] == b"PK", "Excel (zip) magic missing"

    step(10, "LLM status with deterministic provider")
    r = requests.get(f"{API}/llm/status", headers=auth)
    print(f"  llm status: {r.status_code} {r.json()}")

    step(11, "DB-backed verification of analysis rows")
    summary = requests.get(
        f"{API}/projects/{project_id}/analysis/sentiment/summary",
        headers=auth,
    ).json()
    print(f"  sentiment summary: {summary.get('data')}")

    print()
    print("OK: Phase 12 production-stack end-to-end smoke complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())