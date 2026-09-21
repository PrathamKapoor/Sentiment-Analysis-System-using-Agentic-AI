"""Deterministic interpretation text generator.

Used when:
  - the LLM is not configured (no API key, ``LLM_PROVIDER=disabled``, etc.)
  - the LLM call failed (timeout, http_error, malformed, etc.)
  - the LLM is intentionally not invoked (e.g. ``enhanced=False`` report)

The generator must:

  1. Only use numbers that exist in the input. Never invent.
  2. Render a short, conservative, three-section interpretation.
  3. Always include an explicit "this is a deterministic interpretation"
     footer so the report labels it as such, not as LLM output.
  4. Never claim causation.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


FOOTER = (
    "This interpretation was generated deterministically from the verified "
    "metrics above. No large language model was used. If an LLM is configured "
    "for this environment, a richer interpretation can be generated at report "
    "time by selecting the enhanced report mode."
)


def _safe_get(d: Dict[str, Any], *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default


def _format_sentiment(s: Any) -> str:
    if not isinstance(s, dict):
        return ""
    pos = s.get("positive") or {}
    neg = s.get("negative") or {}
    neu = s.get("neutral") or {}
    total = (
        (pos.get("count") or 0)
        + (neg.get("count") or 0)
        + (neu.get("count") or 0)
    )
    if total <= 0:
        return ""
    return (
        f"Of {total} eligible reviews, {pos.get('count', 0)} were positive "
        f"({pos.get('percentage', 0)}%), {neg.get('count', 0)} were negative "
        f"({neg.get('percentage', 0)}%), and {neu.get('count', 0)} were neutral "
        f"({neu.get('percentage', 0)}%)."
    )


def _format_aspects(aspects: Any) -> str:
    if not isinstance(aspects, list) or not aspects:
        return ""
    top = aspects[:5]
    rendered = []
    for a in top:
        if not isinstance(a, dict):
            continue
        name = a.get("name") or a.get("canonicalName") or a.get("aspect")
        if not name:
            continue
        n = a.get("frequency", a.get("count", 0))
        pos = a.get("positivePercentage")
        neg = a.get("negativePercentage")
        bits = [f"{n} mentions"]
        if isinstance(pos, (int, float)) and isinstance(neg, (int, float)):
            bits.append(f"positive {pos}%, negative {neg}%")
        rendered.append(f"{name} ({', '.join(str(b) for b in bits)})")
    return "Most-discussed aspects: " + "; ".join(rendered) + "."


def _format_keywords(keywords: Any) -> str:
    if not isinstance(keywords, list) or not keywords:
        return ""
    top = [k.get("keyword") for k in keywords[:6] if isinstance(k, dict) and k.get("keyword")]
    if not top:
        return ""
    return "Most frequent terms: " + ", ".join(top) + "."


def _format_quality(analytics: Dict[str, Any]) -> str:
    spam = _safe_get(analytics, "spamCount", default=0) or 0
    dup = _safe_get(analytics, "duplicateCount", default=0) or 0
    total = _safe_get(analytics, "totalReviews", default=0) or 0
    eligible = _safe_get(analytics, "eligibleReviews")
    notes = []
    if spam:
        notes.append(f"{spam} spam review(s) excluded")
    if dup:
        notes.append(f"{dup} duplicate review(s) excluded")
    if eligible is not None and total and eligible < total:
        notes.append(f"{eligible} of {total} reviews were eligible for analysis")
    if not notes:
        return ""
    return "Data quality: " + ", ".join(notes) + "."


def generate_deterministic_interpretation(analytics: Dict[str, Any]) -> str:
    """Return a short, conservative interpretation string from analytics
    only. Sections are separated by blank lines. The footer is appended
    so the report can label this as deterministic."""
    lines: List[str] = []

    quality = _format_quality(analytics)
    if quality:
        lines.append("Key signals\n" + quality)

    sentiment = _format_sentiment(_safe_get(analytics, "sentiment"))
    if sentiment:
        lines.append("What the data suggests\n" + sentiment)

    extras = []
    aspects = _format_aspects(_safe_get(analytics, "topAspects") or _safe_get(analytics, "aspects"))
    if aspects:
        extras.append(aspects)
    keywords = _format_keywords(_safe_get(analytics, "topKeywords") or _safe_get(analytics, "keywords"))
    if keywords:
        extras.append(keywords)
    trend = _safe_get(analytics, "trendDirection")
    if isinstance(trend, str) and trend:
        extras.append(f"Recent trend direction: {trend}.")
    if extras:
        lines.append("Additional observations\n" + " ".join(extras))

    # Always include the limitations section, even if empty, so the
    # report has a stable shape.
    lines.append(
        "Limitations to be aware of\n"
        "These are descriptive observations only. They do not establish "
        "causation, do not reflect review text in detail, and do not replace "
        "human review of the underlying reviews and report sections."
    )

    if not lines:
        return "No interpretation could be generated from the available data.\n\n" + FOOTER

    return "\n\n".join(lines) + "\n\n" + FOOTER
