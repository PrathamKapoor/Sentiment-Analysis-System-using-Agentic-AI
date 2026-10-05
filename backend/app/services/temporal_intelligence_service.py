"""Explainable temporal comparisons over dated, eligible persisted reviews."""
from collections import defaultdict
from datetime import date, timedelta

from app.models import Review, AspectSentiment

MAX_REVIEWS_PER_WINDOW = 20000
from app.services.feedback_intelligence_service import classify_feedback


def _bounded_days(value, default):
    try:
        return max(1, min(int(value), 180))
    except (TypeError, ValueError):
        return default


def _window_counts(project_id, days=7, baseline_days=7, *, today=None):
    days = _bounded_days(days, 7)
    baseline_days = _bounded_days(baseline_days, 7)
    today = today or date.today()
    current_start = today - timedelta(days=days - 1)
    baseline_end = current_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=baseline_days - 1)
    base_query = Review.query.filter_by(project_id=project_id).filter(
        Review.deleted_at.is_(None), Review.is_spam.is_(False), Review.is_duplicate.is_(False),
        Review.review_date.isnot(None))
    def window_query(start, end):
        query = base_query.filter(Review.review_date >= start, Review.review_date <= end)
        total = query.count()
        rows = query.order_by(Review.review_date.desc(), Review.id).limit(MAX_REVIEWS_PER_WINDOW + 1).all()
        return rows[:MAX_REVIEWS_PER_WINDOW], total
    baseline, baseline_total = window_query(baseline_start, baseline_end)
    current, current_total = window_query(current_start, today)
    truncated = baseline_total > MAX_REVIEWS_PER_WINDOW or current_total > MAX_REVIEWS_PER_WINDOW
    return baseline, current, {"baselineFrom": baseline_start.isoformat(), "baselineTo": baseline_end.isoformat(),
        "currentFrom": current_start.isoformat(), "currentTo": today.isoformat(),
        "baselineDays": baseline_days, "currentDays": days,
        "baselineEligibleCount": baseline_total, "currentEligibleCount": current_total,
        "sampleLimit": MAX_REVIEWS_PER_WINDOW if truncated else None, "truncated": truncated}


def _signals(reviews):
    rows = defaultdict(lambda: {"count": 0, "evidence": [], "sources": set()})
    review_ids = [review.id for review in reviews]
    aspects_by_review = defaultdict(list)
    if review_ids:
        links = AspectSentiment.query.filter(AspectSentiment.review_id.in_(review_ids)).all()
        for link in links:
            aspects_by_review[link.review_id].append(link)
    for review in reviews:
        source = review.source or "unknown"
        if review.sentiment_result and review.sentiment_result.sentiment_label == "negative":
            row = rows["NEGATIVE_SENTIMENT"]
            row["count"] += 1
            row["sources"].add(source)
            if len(row["evidence"]) < 100:
                row["evidence"].append(str(review.id))
        for category in classify_feedback(review.text or ""):
            name = category["category"]
            if name == "OTHER":
                continue
            row = rows[name]
            row["count"] += 1
            row["sources"].add(source)
            if len(row["evidence"]) < 100:
                row["evidence"].append(str(review.id))
        # Aspect trends use previously persisted aspect analysis only.
        for link in aspects_by_review.get(review.id, []):
            name = "ASPECT:" + (link.aspect.name if link.aspect else "unknown")
            rows[name]["count"] += 1
            rows[name]["sources"].add(source)
            if len(rows[name]["evidence"]) < 100:
                rows[name]["evidence"].append(str(review.id))
    return rows


def get_emerging_themes(project_id, *, days=7, baseline_days=7, minimum_increase=1.5, today=None):
    baseline, current, window = _window_counts(project_id, days, baseline_days, today=today)
    before, after = _signals(baseline), _signals(current)
    items = []
    try:
        threshold = max(1.0, float(minimum_increase))
    except (TypeError, ValueError):
        threshold = 1.5
    for theme in sorted(set(before) | set(after)):
        old, new = before.get(theme, {}).get("count", 0), after.get(theme, {}).get("count", 0)
        rate_ratio = (new / max(window["currentDays"], 1)) / (old / max(window["baselineDays"], 1)) if old else None
        if new < 3 or (old and (rate_ratio is None or rate_ratio < threshold)):
            continue
        items.append({"theme": theme, "baselineCount": old, "currentCount": new,
            "change": new - old, "rateRatio": round(rate_ratio, 3) if rate_ratio is not None else None,
            "baselineWindow": {"from": window["baselineFrom"], "to": window["baselineTo"]},
            "comparisonWindow": {"from": window["currentFrom"], "to": window["currentTo"]},
            "supportingEvidenceIds": after.get(theme, {}).get("evidence", []),
            "sources": sorted(after.get(theme, {}).get("sources", set())),
            "method": "deterministic_category_or_persisted_aspect_rate_comparison_v1"})
    return {"comparison": window, "items": items, "limitations": [
        *([f"Counts use a bounded sample of up to {MAX_REVIEWS_PER_WINDOW} newest eligible reviews per period; totals show full window volume."] if window["truncated"] else []),
        "Only eligible reviews with review dates are included; undated feedback is excluded.",
        "Themes are configured phrase categories or previously analyzed aspects, not semantic clusters.",
        "A comparison period with zero baseline is reported as newly observed, not as an infinite percentage increase."]}


def get_anomalies(project_id, *, days=7, baseline_days=7, minimum_increase=1.5, today=None):
    baseline, current, window = _window_counts(project_id, days, baseline_days, today=today)
    before, after = _signals(baseline), _signals(current)
    try:
        threshold = max(1.0, float(minimum_increase))
    except (TypeError, ValueError):
        threshold = 1.5
    items = []
    # Review volume includes every eligible review, even when no category matched.
    before["REVIEW_VOLUME"] = {"count": len(baseline), "evidence": [str(r.id) for r in baseline[:100]], "sources": {r.source or "unknown" for r in baseline}}
    after["REVIEW_VOLUME"] = {"count": len(current), "evidence": [str(r.id) for r in current[:100]], "sources": {r.source or "unknown" for r in current}}
    for metric in sorted(set(before) | set(after)):
        old, new = before.get(metric, {}).get("count", 0), after.get(metric, {}).get("count", 0)
        ratio = (new / max(window["currentDays"], 1)) / (old / max(window["baselineDays"], 1)) if old else None
        if new >= 3 and (old == 0 or (ratio is not None and ratio >= threshold)):
            items.append({"metric": metric, "baselineCount": old, "currentCount": new,
                "rateRatio": round(ratio, 3) if ratio is not None else None,
                "baselineWindow": {"from": window["baselineFrom"], "to": window["baselineTo"]},
                "comparisonWindow": {"from": window["currentFrom"], "to": window["currentTo"]},
                "evidenceIds": after.get(metric, {}).get("evidence", []),
                "sources": sorted(after.get(metric, {}).get("sources", set())),
                "method": "deterministic_period_rate_comparison_v1"})
    return {"comparison": window, "items": items, "limitations": [
        *([f"Counts use a bounded sample of up to {MAX_REVIEWS_PER_WINDOW} newest eligible reviews per period; totals show full window volume."] if window["truncated"] else []),
        "This is a simple period-rate threshold, not a statistical significance test.",
        "Only eligible dated reviews are included; source mix is shown and may bias comparisons."]}
