"""PDF generation via ReportLab. Chosen over WeasyPrint for this project:
WeasyPrint requires native GTK/Pango/Cairo system libraries that aren't
installable via pip alone and weren't available in this environment (see
README "Testing Notes" — attempted, failed with a missing libgobject-2.0-0).
ReportLab is pure-Python-installable and was verified to actually render a
PDF in this environment before being adopted.

No screenshots of application pages — every table/heading here is built
directly from the same structured data returned by the analysis services.
"""
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", fontSize=20, spaceAfter=6, leading=24))
    styles.add(ParagraphStyle(name="ReportMeta", fontSize=10, textColor=colors.grey, spaceAfter=12))
    styles.add(ParagraphStyle(name="SectionHeading", fontSize=14, spaceBefore=16, spaceAfter=8, leading=18))
    return styles


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(2 * cm, 1 * cm, "AI/System Generated Report — Agentic Sentiment Analysis System")
    canvas.drawRightString(A4[0] - 2 * cm, 1 * cm, f"Page {doc.page}")
    canvas.restoreState()


def _table(headers, rows):
    data = [headers] + rows
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def generate_pdf(file_path, organisation_name, project_name, date_from, date_to, sections_data, skipped_sections):
    styles = _styles()
    doc = SimpleDocTemplate(
        file_path, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )
    story = []

    story.append(Paragraph(f"{project_name} — Sentiment Analysis Report", styles["ReportTitle"]))
    story.append(Paragraph(
        f"Organisation: {organisation_name} &nbsp;|&nbsp; Date range: {date_from} to {date_to} "
        f"&nbsp;|&nbsp; Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        styles["ReportMeta"],
    ))
    story.append(Paragraph(
        "<b>AI/System Generated Report</b> — all figures are computed directly from stored analysis "
        "results. Narrative text is deterministically generated, not written by a human.",
        styles["ReportMeta"],
    ))

    if "projectOverview" in sections_data:
        po = sections_data["projectOverview"]
        story.append(Paragraph("Project Overview", styles["SectionHeading"]))
        story.append(Paragraph(f"Status: {po['status']}. {po.get('description') or ''}", styles["Normal"]))

    if "executiveSummary" in sections_data:
        story.append(Paragraph("Executive Summary", styles["SectionHeading"]))
        story.append(Paragraph(sections_data["executiveSummary"] or "", styles["Normal"]))

    if "sentimentDistribution" in sections_data:
        s = sections_data["sentimentDistribution"]
        story.append(Paragraph("Sentiment Distribution", styles["SectionHeading"]))
        story.append(_table(
            ["Metric", "Value"],
            [
                ["Total reviews", str(s["totalReviews"])],
                ["Analysed reviews", str(s["analysedReviews"])],
                ["Positive", f"{s['positive']['count']} ({s['positive']['percentage']}%)"],
                ["Negative", f"{s['negative']['count']} ({s['negative']['percentage']}%)"],
                ["Neutral", f"{s['neutral']['count']} ({s['neutral']['percentage']}%)"],
                ["Average confidence", str(s["averageConfidence"])],
            ],
        ))

    if "sentimentTrends" in sections_data:
        story.append(Paragraph("Sentiment Trends (Monthly)", styles["SectionHeading"]))
        rows = [[p["period"], str(p["totalReviews"]), f"{p['positivePercentage']}%", f"{p['negativePercentage']}%"]
                for p in sections_data["sentimentTrends"]["periods"]]
        story.append(_table(["Period", "Reviews", "Positive %", "Negative %"], rows))

    if "topicAnalysis" in sections_data:
        story.append(Paragraph("Topic Analysis", styles["SectionHeading"]))
        rows = [[t["topicName"], str(t["reviewCount"])] for t in sections_data["topicAnalysis"]]
        story.append(_table(["Topic", "Reviews"], rows))

    if "keywordAnalysis" in sections_data:
        story.append(Paragraph("Keyword Analysis", styles["SectionHeading"]))
        rows = [[k["keyword"], str(k["frequency"]), k["sentiment"]] for k in sections_data["keywordAnalysis"]]
        story.append(_table(["Keyword", "Frequency", "Sentiment"], rows))

    if "aspectSentiment" in sections_data:
        story.append(Paragraph("Aspect-Based Sentiment", styles["SectionHeading"]))
        rows = [
            [a["name"], str(a["frequency"]), f"{a['positivePercentage']}%", f"{a['negativePercentage']}%"]
            for a in sections_data["aspectSentiment"]
        ]
        story.append(_table(["Aspect", "Frequency", "Positive %", "Negative %"], rows))

    if "recommendations" in sections_data:
        story.append(Paragraph("Recommendations", styles["SectionHeading"]))
        rows = [[r["text"], r["priority"], r["status"]] for r in sections_data["recommendations"]]
        story.append(_table(["Recommendation", "Priority", "Status"], rows))

    if "alerts" in sections_data:
        story.append(Paragraph("Alerts", styles["SectionHeading"]))
        rows = [[a["name"], a["severity"], a["status"]] for a in sections_data["alerts"]]
        story.append(_table(["Alert", "Severity", "Status"], rows))

    if "representativeReviews" in sections_data:
        story.append(Paragraph("Representative Reviews", styles["SectionHeading"]))
        for r in sections_data["representativeReviews"][:20]:
            story.append(Paragraph(f"&bull; {r['text']}", styles["Normal"]))

    if "conclusion" in sections_data:
        story.append(Paragraph("Conclusion", styles["SectionHeading"]))
        story.append(Paragraph(sections_data["conclusion"], styles["Normal"]))

    if skipped_sections:
        story.append(Spacer(1, 12))
        story.append(Paragraph(
            f"<i>Sections omitted (no data available for the selected range): {', '.join(skipped_sections)}</i>",
            styles["ReportMeta"],
        ))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
