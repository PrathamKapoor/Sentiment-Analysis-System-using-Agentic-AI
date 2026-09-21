#!/usr/bin/env bash
# Phase 12 end-to-end smoke test.
# Drives the running production stack through a real user workflow.
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:5000}"
API="$BASE/api/v1"
TS="$(date +%s)"
EMAIL="phase12-e2e-${TS}@stack.test"
PASS="Phase12TestPass!"

echo "[1] register"
REG=$(curl -fsS -X POST "$API/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"E2E Owner ${TS}\",\"email\":\"${EMAIL}\",\"password\":\"${PASS}\",\"organisationName\":\"E2E Org ${TS}\"}")
ACCESS=$(echo "$REG" | python -c "import sys,json;print(json.load(sys.stdin)['data']['accessToken'])")
ORG=$(echo "$REG" | python -c "import sys,json;print(json.load(sys.stdin)['data']['organisationId'])")
echo "  user ok  org=$ORG"

AUTH=(-H "Authorization: Bearer $ACCESS" -H "X-Organisation-Id: $ORG")

echo "[2] create project"
PROJ=$(curl -fsS -X POST "$API/projects" "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"E2E Project ${TS}\",\"description\":\"phase12 e2e\"}")
PROJECT_ID=$(echo "$PROJ" | python -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
echo "  project ok  id=$PROJECT_ID"

echo "[3] upload dataset (CSV)"
DATASET="C:/Sentiment_Analysis_Management_System_using_Agentic_AI/database/demo_dataset.csv"
if [ ! -f "$DATASET" ]; then
  echo "  FAIL: demo dataset not found at $DATASET"
  exit 1
fi
SIZE=$(wc -c < "$DATASET" | tr -d ' ')
echo "  csv size: $SIZE bytes"
UP=$(curl -fsS -X POST "$API/projects/${PROJECT_ID}/datasets" "${AUTH[@]}" \
  -F "file=@${DATASET}" \
  -F "name=phase12-e2e-${TS}")
DATASET_ID=$(echo "$UP" | python -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
echo "  dataset ok  id=$DATASET_ID"

echo "[4] process dataset"
curl -fsS -X POST "$API/projects/${PROJECT_ID}/datasets/${DATASET_ID}/process" "${AUTH[@]}" \
  -o /dev/null -w "  process status=%{http_code}\n"

echo "[5] sentiment analysis"
curl -fsS -X POST "$API/projects/${PROJECT_ID}/analysis/sentiment" "${AUTH[@]}" \
  -o /dev/null -w "  sentiment status=%{http_code}\n"

echo "[6] topic analysis"
curl -fsS -X POST "$API/projects/${PROJECT_ID}/analysis/topics" "${AUTH[@]}" \
  -o /dev/null -w "  topic status=%{http_code}\n"

echo "[7] aspect analysis"
curl -fsS -X POST "$API/projects/${PROJECT_ID}/analysis/aspects" "${AUTH[@]}" \
  -o /dev/null -w "  aspect status=%{http_code}\n"

echo "[8] PDF report"
PDF=$(curl -fsS -X POST "$API/projects/${PROJECT_ID}/reports" "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"format\":\"pdf\",\"title\":\"Phase12 PDF Report\"}")
REPORT_ID=$(echo "$PDF" | python -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
echo "  pdf report id=$REPORT_ID"
curl -fsS "$API/projects/${PROJECT_ID}/reports/${REPORT_ID}/download" "${AUTH[@]}" \
  -o /tmp/phase12_pdf_report.pdf -w "  pdf download status=%{http_code} bytes=%{size_download}\n"

echo "[9] Excel report"
XLS=$(curl -fsS -X POST "$API/projects/${PROJECT_ID}/reports" "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"format\":\"excel\",\"title\":\"Phase12 Excel Report\"}")
XREPORT_ID=$(echo "$XLS" | python -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
echo "  excel report id=$XREPORT_ID"
curl -fsS "$API/projects/${PROJECT_ID}/reports/${XREPORT_ID}/download" "${AUTH[@]}" \
  -o /tmp/phase12_xlsx_report.xlsx -w "  excel download status=%{http_code} bytes=%{size_download}\n"

echo "[10] LLM status (deterministic provider)"
curl -fsS "$API/llm/status" "${AUTH[@]}" \
  -o /tmp/phase12_llm_status.json -w "  llm status status=%{http_code}\n"

echo "DONE"