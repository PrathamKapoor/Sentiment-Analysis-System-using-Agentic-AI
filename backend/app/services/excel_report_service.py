"""Excel generation via OpenPyXL — structured worksheets with headers and
reasonable column widths, not a raw JSON dump.
"""
from datetime import datetime as dt, date, timezone

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill(start_color="0D6EFD", end_color="0D6EFD", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def _parse_date(value):
    """Report data arrives as ISO strings (same shape the PDF renderer
    consumes) — parse back to a real date so Excel treats the column as a
    date, not text. Never raises/fabricates: an unparseable value is left
    as-is rather than crashing report generation over a formatting nicety.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return value


def _parse_datetime(value):
    if not value:
        return None
    try:
        return dt.fromisoformat(str(value))
    except ValueError:
        return value


def _write_sheet(wb, title, headers, rows, widths=None, date_columns=None):
    """date_columns: optional {1-indexed column: number_format} applied to
    that column's data cells (header row excluded).
    """
    ws = wb.create_sheet(title=title[:31])  # Excel sheet-name length limit
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    for row in rows:
        # Spreadsheet applications interpret leading =, +, -, and @ as
        # formulas. Review text and source labels are untrusted content, so
        # preserve them as literal strings in exported workbooks.
        ws.append([_safe_cell_value(value) for value in row])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(len(rows) + 1, 1)}"
    for idx, width in enumerate(widths or [20] * len(headers), start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    for col_idx, number_format in (date_columns or {}).items():
        for row_idx in range(2, len(rows) + 2):
            ws.cell(row=row_idx, column=col_idx).number_format = number_format
    return ws


def _safe_cell_value(value):
    formula_prefixes = ("=", "+", "-", "@")
    if isinstance(value, str) and value.lstrip(" \t\r\n\ufeff").startswith(formula_prefixes):
        return "'" + value
    return value


def generate_excel(file_path, organisation_name, project_name, date_from, date_to, sections_data, skipped_sections):
    wb = Workbook()
    wb.remove(wb.active)  # drop the default blank sheet

    summary_rows = [
        ["Organisation", organisation_name],
        ["Project", project_name],
        ["Date range", f"{date_from or 'all'} to {date_to or 'all'}"],
        ["Generated", dt.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")],
        ["Report type", "AI/System Generated"],
    ]
    if skipped_sections:
        summary_rows.append(["Sections omitted (no data)", ", ".join(skipped_sections)])
    _write_sheet(wb, "Summary", ["Field", "Value"], summary_rows, widths=[28, 50])

    if "sentimentDistribution" in sections_data:
        s = sections_data["sentimentDistribution"]
        _write_sheet(wb, "Sentiment", ["Metric", "Value"], [
            ["Total reviews", s["totalReviews"]],
            ["Analysed reviews", s["analysedReviews"]],
            ["Positive count", s["positive"]["count"]],
            ["Positive %", s["positive"]["percentage"]],
            ["Negative count", s["negative"]["count"]],
            ["Negative %", s["negative"]["percentage"]],
            ["Neutral count", s["neutral"]["count"]],
            ["Neutral %", s["neutral"]["percentage"]],
            ["Winning-label score (avg, not prob.)", s["averageConfidence"]],
        ])

    if "topicAnalysis" in sections_data:
        rows = [[t["topicName"], t["reviewCount"]] for t in sections_data["topicAnalysis"]]
        _write_sheet(wb, "Topics", ["Topic", "Review Count"], rows)

    if "keywordAnalysis" in sections_data:
        rows = [
            [k["keyword"], k["frequency"], k["sentiment"], k["positiveCount"], k["negativeCount"], k["neutralCount"]]
            for k in sections_data["keywordAnalysis"]
        ]
        _write_sheet(wb, "Keywords", ["Keyword", "Frequency", "Sentiment", "Positive", "Negative", "Neutral"], rows)

    if "aspectSentiment" in sections_data:
        rows = [
            [a["name"], a["frequency"], a["positivePercentage"], a["negativePercentage"], a["neutralPercentage"], a["averageConfidence"]]
            for a in sections_data["aspectSentiment"]
        ]
        _write_sheet(wb, "Aspects", ["Aspect", "Frequency", "Positive %", "Negative %", "Neutral %", "Avg Confidence"], rows)

    if "recommendations" in sections_data:
        rows = [
            [r["text"], r["priority"], r["status"], r["aspectName"] or "", r["supportingReviewCount"]]
            for r in sections_data["recommendations"]
        ]
        _write_sheet(wb, "Recommendations", ["Recommendation", "Priority", "Status", "Aspect", "Supporting Reviews"], rows, widths=[60, 12, 12, 20, 18])

    if "alerts" in sections_data:
        rows = [
            [a["name"], a["severity"], a["status"], a["metric"], a["thresholdValue"], _parse_datetime(a["triggeredAt"])]
            for a in sections_data["alerts"]
        ]
        _write_sheet(
            wb, "Alerts", ["Alert", "Severity", "Status", "Metric", "Threshold", "Triggered At"], rows,
            date_columns={6: "YYYY-MM-DD HH:MM"},
        )

    if "representativeReviews" in sections_data:
        rows = [
            [r["text"], r["source"] or "", r["rating"], _parse_date(r["reviewDate"])]
            for r in sections_data["representativeReviews"]
        ]
        _write_sheet(
            wb, "Reviews", ["Text", "Source", "Rating", "Date"], rows, widths=[70, 20, 10, 15],
            date_columns={4: "YYYY-MM-DD"},
        )

    if "securityFindings" in sections_data:
        rows = []
        for finding in sections_data["securityFindings"]:
            evidence = " | ".join(
                str(item.get("text", "")) for item in finding.get("evidence", [])
            )
            rows.append([
                finding["findingType"], finding["severity"], finding["status"],
                finding.get("confidence"), finding["classificationMethod"],
                finding["reviewId"], finding.get("source") or "unknown",
                finding.get("sourceUrl") or "", finding.get("reviewDate"),
                finding.get("retrievedAt"), evidence,
            ])
        _write_sheet(
            wb, "Security Findings",
            ["Finding", "Severity", "Status", "Confidence (null = uncalibrated)",
             "Classification Method", "Review ID", "Source", "Source URL", "Review Date",
             "Retrieved At", "Evidence"],
            rows, widths=[28, 14, 18, 24, 30, 38, 18, 45, 16, 28, 70],
            date_columns={9: "YYYY-MM-DD", 10: "YYYY-MM-DD HH:MM"},
        )

    if "investigationFindings" in sections_data:
        investigation = sections_data["investigationFindings"]
        rows = [["Question", investigation["question"]], ["Status", investigation["status"]],
                ["Semantic synthesis", investigation.get("semanticSynthesis", {}).get("status", "unavailable")],
                ["Answer", investigation.get("answer", "")]]
        for finding in investigation.get("findings", []):
            rows.append([finding["status"], finding["type"], finding["claim"], finding["reviewState"], finding.get("recommendedAction") or ""])
            for evidence in finding.get("evidence", []):
                rows.append(["Evidence", evidence["evidenceId"], evidence["source"], evidence.get("date") or "", evidence["text"]])
        _write_sheet(wb, "Investigation", ["Type", "Finding", "Claim / value", "Review state", "Evidence / action"], rows, widths=[22, 38, 90, 22, 90])

    if "sourceProvenance" in sections_data:
        provenance = sections_data["sourceProvenance"]
        rows = [[
            source["source"], source["sourceType"], source["originId"],
            source["collectionMethod"], source.get("sourceUrl") or "",
            source["recordCount"], source.get("canonicalEvidenceCount", source["recordCount"]),
            source.get("duplicateRecordCount", 0), source.get("duplicateRelationshipCount", 0),
            source.get("samplingNote", ""), _parse_date(source.get("firstReviewDate")),
            _parse_date(source.get("lastReviewDate")), source["undatedRecordsIncluded"],
            ", ".join(str(level) for level in source.get("collectionLevels", [])),
            ", ".join(source.get("providers", [])),
            ", ".join(f"{key}:{value}" for key, value in sorted(source.get("identityMatchStatusCounts", {}).items())),
            source.get("collectionMetadataSampledRecords", 0),
        ] for source in provenance["sources"]]
        _write_sheet(
            wb, "Sources",
            ["Source", "Type", "Origin ID", "Collection Method", "Source URL",
             "Eligible Source Records", "Canonical Evidence", "Duplicate Records", "Duplicate Relationships",
             "Sampling Limitation", "First Review Date", "Last Review Date", "Undated Included",
             "Collection Levels", "Providers", "Identity Match Counts", "Metadata Sample Size"],
            rows, widths=[24, 20, 38, 55, 45, 22, 20, 20, 24, 55, 18, 18, 20, 18, 24, 30, 18],
            date_columns={11: "YYYY-MM-DD", 12: "YYYY-MM-DD"},
        )
        wb["Sources"].append(["Project totals", "", "", "", "", provenance.get("recordCount", 0),
            provenance.get("canonicalEvidenceCount", 0), "", provenance.get("duplicateRelationshipCount", 0),
            provenance.get("definition", "")])
        if provenance.get("truncated"):
            wb["Sources"].append([
                f"Truncated to top {provenance['maxSources']} source groups by eligible record count."
            ])

    if "methodology" in sections_data:
        methodology = sections_data["methodology"]
        rows = [
            ["Report period", f"{methodology.get('dateFrom') or 'unspecified'} to {methodology.get('dateTo') or 'unspecified'}"],
        ]
        rows.extend([[item["label"], item["meaning"]] for item in methodology.get("trustLabels", [])])
        rows.extend([["Method", method] for method in methodology.get("methods", [])])
        rows.extend([["Limitation", limitation] for limitation in methodology.get("limitations", [])])
        _write_sheet(wb, "Methodology", ["Category", "Description"], rows, widths=[28, 110])

    if "aiInterpretation" in sections_data:
        meta = sections_data["aiInterpretation"]
        source = meta.get("source", "deterministic")
        # Same labelling contract as the PDF renderer: "AI-Generated" is
        # only used when a live LLM produced the text. The deterministic
        # fallback is named as a summary, not as AI-generated.
        source_label = "AI-Generated Contextual Interpretation (LLM)" if source == "llm" \
            else "Deterministic Contextual Summary"
        rows = [
            ["Source", source_label],
            ["Provider", meta.get("provider") or ""],
            ["Model", meta.get("model") or ""],
            ["Status", meta.get("status") or ""],
            ["Latency (ms)", int(meta.get("latencyMs") or 0)],
            ["Warning", (meta.get("warning") or "")[:500]],
            ["Notice", (
                "This section was produced by a language model and is not a measured finding."
                if meta.get("source") == "llm"
                else "This section was produced deterministically from the verified metrics. No LLM was used."
            )],
            ["Interpretation", meta.get("text", "")],
        ]
        # Sheet name reflects the source so an auditor opening the file
        # sees the provenance immediately.
        sheet_title = "AI Interpretation" if meta.get("source") == "llm" else "Deterministic Summary"
        _write_sheet(wb, sheet_title, ["Field", "Value"], rows, widths=[28, 100])

    wb.save(file_path)
