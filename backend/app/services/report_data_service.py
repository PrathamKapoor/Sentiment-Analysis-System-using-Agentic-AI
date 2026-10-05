"""Gathers report content from existing analytics services — nothing is
computed specially for reports; every number is the same one already shown
on the corresponding analysis page. Sections with no underlying data are
omitted from the report (never fabricated), and reported back as
`sectionsSkipped` so the caller knows what was left out and why.
"""
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from app.models import Review, Alert, SecurityFinding, DataSource, Dataset, Investigation, ReviewDuplicateLink
from app.services import (
    sentiment_service, topic_service, keyword_service, aspect_service,
    recommendation_service, trend_service,
)

# A report section that holds AI-generated interpretation, never raw
# numbers. Only included when the report is generated in ``enhanced``
# mode AND the caller passed an ``ai_interpretation`` dict.
AI_INTERPRETATION_SECTION = "aiInterpretation"

ALL_SECTIONS = (
    "projectOverview", "executiveSummary", "sentimentDistribution", "sentimentTrends",
    "topicAnalysis", "keywordAnalysis", "aspectSentiment", "recommendations",
    "comparison", "alerts", "representativeReviews", "conclusion",
    "securityFindings",
    "investigationFindings",
    AI_INTERPRETATION_SECTION,
)


def _safe_source_url(value):
    if not value:
        return None
    from urllib.parse import urlsplit, urlunsplit

    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return None
        host = parts.hostname
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, "", ""))
    except ValueError:
        return None


def _source_provenance(project, date_from, date_to, limit):
    from sqlalchemy import func, or_

    query = (
        Review.query.with_entities(
            Review.data_source_id, Review.dataset_id, Review.source,
            func.count(Review.id), func.count(Review.review_date),
            func.min(Review.review_date), func.max(Review.review_date),
        )
        .filter(
            Review.project_id == project.id,
            Review.deleted_at.is_(None),
            Review.is_spam.is_(False),
            Review.is_duplicate.is_(False),
        )
    )
    if date_from is not None:
        query = query.filter(or_(Review.review_date.is_(None), Review.review_date >= date_from))
    if date_to is not None:
        query = query.filter(or_(Review.review_date.is_(None), Review.review_date <= date_to))
    grouped = (
        query.group_by(Review.data_source_id, Review.dataset_id, Review.source)
        .order_by(func.count(Review.id).desc())
        .limit(limit + 1)
        .all()
    )
    truncated = len(grouped) > limit
    grouped = grouped[:limit]

    source_ids = {row[0] for row in grouped if row[0]}
    dataset_ids = {row[1] for row in grouped if row[1]}
    sources = {str(item.id): item for item in DataSource.query.filter(DataSource.id.in_(source_ids)).all()} if source_ids else {}
    datasets = {str(item.id): item for item in Dataset.query.filter(Dataset.id.in_(dataset_ids)).all()} if dataset_ids else {}

    entries = []
    for source_id, dataset_id, review_source, count, dated_count, first_date, last_date in grouped:
        observed_methods, observed_levels, observed_providers, match_statuses = set(), set(), set(), {}
        if source_id:
            origin = sources.get(str(source_id))
            origin_type = origin.type if origin else "unavailable_source_record"
            label = review_source or origin_type
            source_url = _safe_source_url(origin.url) if origin else None
            collection_method = "configured source collector; adapter provenance is not more specific"
            origin_id = str(source_id)
            sample_query = Review.query.filter(
                Review.project_id == project.id, Review.data_source_id == source_id,
                Review.source == review_source, Review.deleted_at.is_(None),
                Review.is_spam.is_(False), Review.is_duplicate.is_(False),
            )
            if date_from is not None:
                sample_query = sample_query.filter(or_(Review.review_date.is_(None), Review.review_date >= date_from))
            if date_to is not None:
                sample_query = sample_query.filter(or_(Review.review_date.is_(None), Review.review_date <= date_to))
            metadata_sample_limit = max(1, min(int(limit), 100))
            metadata_rows = sample_query.with_entities(Review.source_metadata).limit(metadata_sample_limit).all()
            for (metadata,) in metadata_rows:
                metadata = metadata if isinstance(metadata, dict) else {}
                collection = metadata.get("collection") if isinstance(metadata.get("collection"), dict) else {}
                identity = metadata.get("identityMatch") if isinstance(metadata.get("identityMatch"), dict) else {}
                if collection.get("method"):
                    observed_methods.add(str(collection["method"])[:100])
                if collection.get("level") in {1, 2, 3}:
                    observed_levels.add(int(collection["level"]))
                if collection.get("provider"):
                    observed_providers.add(str(collection["provider"])[:100])
                if identity.get("status") in {"verified", "uncertain", "rejected", "configured_source"}:
                    state = identity["status"]
                    match_statuses[state] = match_statuses.get(state, 0) + 1
            if observed_methods:
                collection_method = ", ".join(sorted(observed_methods)) + f" (observed in up to {len(metadata_rows)} records)"
        else:
            origin = datasets.get(str(dataset_id))
            label = review_source or "uploaded dataset"
            source_url = None
            collection_method = "uploaded dataset"
            origin_type = origin.file_type if origin else "unavailable_dataset_record"
            origin_id = str(dataset_id) if dataset_id else None
        entries.append({
            "source": label, "sourceType": origin_type, "originId": origin_id,
            "collectionMethod": collection_method, "sourceUrl": source_url,
            "recordCount": int(count),
            "collectionLevels": sorted(observed_levels),
            "collectionMethods": sorted(observed_methods),
            "providers": sorted(observed_providers),
            "identityMatchStatusCounts": match_statuses,
            "collectionMetadataSampledRecords": len(metadata_rows) if source_id else 0,
            "firstReviewDate": first_date.isoformat() if first_date else None,
            "lastReviewDate": last_date.isoformat() if last_date else None,
            "undatedRecordsIncluded": dated_count < count,
        })
    # Add cross-source canonical counts without deleting/merging source rows.
    eligible = Review.query.filter(Review.project_id == project.id,
        Review.deleted_at.is_(None), Review.is_spam.is_(False), Review.is_duplicate.is_(False))
    if date_from is not None:
        eligible = eligible.filter(or_(Review.review_date.is_(None), Review.review_date >= date_from))
    if date_to is not None:
        eligible = eligible.filter(or_(Review.review_date.is_(None), Review.review_date <= date_to))
    records = eligible.with_entities(Review.id, Review.data_source_id, Review.dataset_id).all()
    ids = {str(row.id) for row in records}
    links = ReviewDuplicateLink.query.filter(ReviewDuplicateLink.project_id == project.id,
        ReviewDuplicateLink.review_id.in_(ids),
        ReviewDuplicateLink.duplicate_review_id.in_(ids)).all() if ids else []
    duplicate_ids = {str(link.duplicate_review_id) for link in links}
    by_origin = {}
    for row in records:
        key = ("data_source", str(row.data_source_id)) if row.data_source_id else ("dataset", str(row.dataset_id))
        by_origin.setdefault(key, set()).add(str(row.id))
    for entry in entries:
        origin_key = ("data_source" if entry["originId"] in sources else "dataset", entry["originId"])
        origin_ids = by_origin.get(origin_key, set())
        entry["canonicalEvidenceCount"] = len(origin_ids - duplicate_ids)
        entry["duplicateRecordCount"] = len(origin_ids & duplicate_ids)
        entry["duplicateRelationshipCount"] = sum(1 for link in links
            if str(link.review_id) in origin_ids or str(link.duplicate_review_id) in origin_ids)
        source_type = (entry["sourceType"] or "").lower()
        entry["samplingNote"] = {
            "reddit": "Discussion/community sampling; not representative.",
            "github_issues": "Technical issue reports; not representative consumer feedback.",
            "amazon": "Self-selected marketplace reviewers.",
            "flipkart": "Self-selected marketplace reviewers.",
        }.get(source_type, "Source-specific sampling limitations are not characterized.")
    canonical_count = len(ids - duplicate_ids)
    entries.sort(key=lambda row: (row["source"], row["originId"] or ""))
    return {"sources": entries, "maxSources": limit, "truncated": truncated,
            "recordCount": len(ids), "canonicalEvidenceCount": canonical_count,
            "duplicateRelationshipCount": len(links),
            "definition": "Canonical counts treat only explicit stored duplicate relationships as one evidence group; source record counts remain unchanged."}


def gather_report_data(
    project,
    sections,
    date_from,
    date_to,
    ai_summary=None,
    ai_interpretation: Optional[Dict[str, Any]] = None,
    investigation_id: Optional[str] = None,
):
    filters = {"dateFrom": date_from, "dateTo": date_to}
    data = {}
    skipped = []
    max_rows = current_app.config.get("MAX_REPORT_REVIEW_ROWS", 500)
    data["sourceProvenance"] = _source_provenance(project, date_from, date_to, max_rows)

    if "projectOverview" in sections:
        data["projectOverview"] = {
            "name": project.name, "description": project.description,
            "status": project.status, "dateRangeStart": str(date_from), "dateRangeEnd": str(date_to),
        }

    if "executiveSummary" in sections:
        if ai_summary:
            data["executiveSummary"] = ai_summary.content.get("sections", {}).get("overall")
        else:
            skipped.append("executiveSummary")

    if "sentimentDistribution" in sections:
        summary = sentiment_service.get_summary(project.id, filters)
        if summary["analysedReviews"] > 0:
            data["sentimentDistribution"] = summary
        else:
            skipped.append("sentimentDistribution")

    if "sentimentTrends" in sections:
        trends = trend_service.get_trends(project.id, "monthly", filters)
        if trends["periods"]:
            data["sentimentTrends"] = trends
        else:
            skipped.append("sentimentTrends")

    if "topicAnalysis" in sections:
        topics = topic_service.list_topics(project.id)
        if topics:
            # list_topics() returns serialised dicts (Topic.to_dict), so this
            # must be key access, not attribute access. Both renderers read
            # sections_data["topicAnalysis"] entries as dicts with exactly
            # these two keys (excel_report_service.py, pdf_report_service.py).
            data["topicAnalysis"] = [
                {"topicName": t["topicName"], "reviewCount": t["reviewCount"]}
                for t in topics
            ]
        else:
            skipped.append("topicAnalysis")

    if "keywordAnalysis" in sections:
        keywords = keyword_service.extract_keywords(project.id, filters=filters, top_n=20)
        if keywords:
            data["keywordAnalysis"] = keywords
        else:
            skipped.append("keywordAnalysis")

    if "aspectSentiment" in sections:
        aspects = aspect_service.list_aspects(project.id, filters)
        if aspects:
            data["aspectSentiment"] = aspects
        else:
            skipped.append("aspectSentiment")

    if "recommendations" in sections:
        recs = recommendation_service.list_recommendations(project.id)
        if recs:
            data["recommendations"] = [r.to_dict() for r in recs]
        else:
            skipped.append("recommendations")

    if "comparison" in sections:
        # Comparison requires an explicit target project list — not
        # meaningful as a single-project report section without one.
        skipped.append("comparison")

    if "alerts" in sections:
        alerts = Alert.query.filter_by(project_id=project.id).all()
        if alerts:
            data["alerts"] = [a.to_dict() for a in alerts]
        else:
            skipped.append("alerts")

    if "representativeReviews" in sections:
        reviews_query = Review.query.filter_by(
            project_id=project.id, is_spam=False, is_duplicate=False,
        ).filter(Review.deleted_at.is_(None))
        if date_from is not None:
            from sqlalchemy import or_
            reviews_query = reviews_query.filter(
                or_(Review.review_date.is_(None), Review.review_date >= date_from)
            )
        if date_to is not None:
            from sqlalchemy import or_
            reviews_query = reviews_query.filter(
                or_(Review.review_date.is_(None), Review.review_date <= date_to)
            )
        reviews = reviews_query.order_by(Review.created_at.desc()).limit(max_rows).all()
        if reviews:
            data["representativeReviews"] = [{
                "text": r.text, "source": r.source or "",
                "rating": r.rating,
                "reviewDate": r.review_date.isoformat() if r.review_date else None,
            } for r in reviews]
        else:
            skipped.append("representativeReviews")

    if "securityFindings" in sections:
        findings_query = (
            SecurityFinding.query
            .join(Review, SecurityFinding.review_id == Review.id)
            .filter(
                SecurityFinding.project_id == project.id,
                SecurityFinding.organisation_id == project.organisation_id,
                Review.deleted_at.is_(None),
            )
        )
        if date_from is not None:
            from sqlalchemy import or_
            findings_query = findings_query.filter(
                or_(Review.review_date.is_(None), Review.review_date >= date_from)
            )
        if date_to is not None:
            from sqlalchemy import or_
            findings_query = findings_query.filter(
                or_(Review.review_date.is_(None), Review.review_date <= date_to)
            )
        findings = findings_query.order_by(SecurityFinding.created_at.desc()).limit(max_rows).all()
        if findings:
            source_ids = {finding.review.data_source_id for finding in findings if finding.review.data_source_id}
            sources = {
                str(source.id): source
                for source in DataSource.query.filter(DataSource.id.in_(source_ids)).all()
            } if source_ids else {}
            rows = []
            for finding in findings:
                review = finding.review
                source_url = None
                source_kind = "dataset" if review.dataset_id else "unknown"
                if review.data_source_id:
                    data_source = sources.get(str(review.data_source_id))
                    if data_source:
                        source_kind = data_source.type
                        source_url = _safe_source_url(review.source_url) or _safe_source_url(data_source.url)
                rows.append({
                    "id": str(finding.id), "reviewId": str(review.id),
                    "findingType": finding.finding_type, "severity": finding.severity,
                    "confidence": finding.confidence, "evidence": finding.evidence or [],
                    "indicators": finding.indicators or [],
                    "classificationMethod": finding.classification_method,
                    "status": finding.status, "source": review.source or source_kind,
                    "sourceUrl": source_url,
                    "reviewDate": review.review_date.isoformat() if review.review_date else None,
                    "retrievedAt": (
                        review.source_collected_at.isoformat() if review.source_collected_at
                        else review.created_at.isoformat() if review.created_at else None
                    ),
                })
            data["securityFindings"] = rows
        else:
            skipped.append("securityFindings")

    if "investigationFindings" in sections:
        investigation = Investigation.query.filter_by(
            id=investigation_id, project_id=project.id,
            organisation_id=project.organisation_id,
        ).first() if investigation_id else None
        if investigation is None or investigation.status not in {"COMPLETED", "NEEDS_REVIEW", "LIMIT_REACHED"}:
            skipped.append("investigationFindings")
        else:
            evidence_ids = {str(evidence_id) for finding in investigation.findings
                            for evidence_id in (finding.evidence_ids or [])}
            evidence_rows = Review.query.filter(Review.project_id == project.id,
                Review.id.in_(evidence_ids), Review.deleted_at.is_(None),
                Review.is_spam.is_(False), Review.is_duplicate.is_(False)).all() if evidence_ids else []
            evidence = {str(review.id): {"source": review.source or "unknown",
                "date": review.review_date.isoformat() if review.review_date else None,
                "text": review.text[:1000]} for review in evidence_rows}
            findings = []
            for finding in investigation.findings:
                valid_ids = [str(item) for item in (finding.evidence_ids or []) if str(item) in evidence]
                if valid_ids:
                    findings.append({"type": finding.finding_type, "status": finding.claim_status,
                        "claim": finding.claim, "reviewState": finding.review_state,
                        "recommendedAction": finding.recommended_action,
                        "evidence": [{"evidenceId": item, **evidence[item]} for item in valid_ids]})
            data["investigationFindings"] = {"question": investigation.question,
                "status": investigation.status, "answer": (investigation.result_summary or {}).get("answer", ""),
                "semanticSynthesis": (investigation.result_summary or {}).get("semanticSynthesis", {}),
                "toolsConsulted": (investigation.result_summary or {}).get("toolsConsulted", []),
                "sourceComposition": (investigation.result_summary or {}).get("sourceComposition", []),
                "findings": findings, "evidenceCount": len(evidence)}

    if "conclusion" in sections:
        sentiment = data.get("sentimentDistribution")
        aspects = data.get("aspectSentiment")
        if sentiment and aspects:
            # sentiment_service.get_summary() returns each bucket as
            # {"count", "percentage"} with no "label" key, so the winning
            # label is the dict key itself, not a field on the value.
            dominant_label, dominant = max(
                (
                    ("positive", sentiment["positive"]),
                    ("negative", sentiment["negative"]),
                    ("neutral", sentiment["neutral"]),
                ),
                key=lambda kv: kv[1]["count"],
            )
            top_aspect = aspects[0]["name"] if aspects else None
            data["conclusion"] = (
                f"Based on {sentiment['analysedReviews']} reviews, the dominant sentiment is "
                f"{dominant_label} ({dominant['percentage']}%). The most-discussed aspect is "
                f"\"{top_aspect}\"."
            )
        else:
            skipped.append("conclusion")

    if AI_INTERPRETATION_SECTION in sections:
        if ai_interpretation and ai_interpretation.get("text"):
            data[AI_INTERPRETATION_SECTION] = {
                "text": ai_interpretation.get("text", ""),
                "source": ai_interpretation.get("source", "deterministic"),
                "provider": ai_interpretation.get("provider"),
                "model": ai_interpretation.get("model"),
                "status": ai_interpretation.get("status", "ok"),
                "latencyMs": ai_interpretation.get("latencyMs", 0),
                "warning": ai_interpretation.get("warning"),
            }
        else:
            skipped.append(AI_INTERPRETATION_SECTION)

    # Every export carries an explicit interpretation boundary, even when
    # the caller selects only a single analytic section.
    data["methodology"] = {
        "trustLabels": [
            {"label": "FACT", "meaning": "A stored value or deterministic calculation from this project's data; each section's period and exclusions apply."},
            {"label": "OBSERVATION", "meaning": "A repeated or rule-matched pattern in the available feedback; it does not prove an external event."},
            {"label": "MODEL INTERPRETATION", "meaning": "Contextual wording generated by an optional model; not a measured finding."},
            {"label": "HYPOTHESIS", "meaning": "A possible explanation. This report does not claim causal root causes."},
            {"label": "RECOMMENDATION", "meaning": "Advisory guidance; no action is executed automatically."},
        ],
        "methods": [
            f"Sentiment results use stored model metadata; configured engine: {current_app.config.get('SENTIMENT_ENGINE', 'vader')}.",
            "Topics use the project's deterministic TF-IDF and clustering analysis.",
            "Security entries are deterministic phrase signals linked to source reviews; confidence is uncalibrated and a signal is not a confirmed incident.",
            "Optional model interpretation, when present, is separately labelled and never supplies measured counts.",
        ],
        "limitations": [
            "Source samples can be incomplete and biased; counts from different channels are not directly comparable without suitable denominators.",
            "Undated eligible review records are included in date-bounded sections and remain explicitly undated; the source appendix flags where they are included.",
            "Source record counts exclude deleted, spam, and duplicate reviews. Undated reviews are included when a date bound is selected.",
            f"Source provenance lists at most {max_rows} origin groups, ordered by eligible record count.",
            "Absence of a detected security signal does not establish that a product or organization is secure.",
            "This report does not infer or validate a causal root cause.",
        ],
        "dateFrom": date_from.isoformat() if hasattr(date_from, "isoformat") else date_from,
        "dateTo": date_to.isoformat() if hasattr(date_to, "isoformat") else date_to,
    }

    return data, skipped
