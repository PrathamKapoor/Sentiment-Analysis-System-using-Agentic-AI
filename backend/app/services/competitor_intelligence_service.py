"""Deterministic competitor and explicit switching evidence from project reviews."""
import re

from app.models import ProjectEntity, Review


_SWITCH_PREFIXES = (
    re.compile(r"\b(?:switch(?:ing|ed)?|mov(?:e|ing|ed))\s+(?:from\s+.{1,80}?\s+)?to\s+", re.IGNORECASE),
    re.compile(r"\b(?:leav(?:e|ing|es)|mov(?:e|ing|ed))\s+.{1,80}?\s+for\s+", re.IGNORECASE),
    re.compile(r"\bchoos(?:e|ing|es)?\s+", re.IGNORECASE),
    re.compile(r"\breplac(?:e|ing|ed)\s+.{1,80}?\s+with\s+", re.IGNORECASE),
)
_REASON = re.compile(r"\b(?:because|since|as)\s+([^.!?\n]{1,240})", re.IGNORECASE)


def _sentences(text):
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]|$)", text):
        start, end = match.span()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            yield start, end


def _term_matches(text, term):
    pattern = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)
    return list(pattern.finditer(text))


def _switching_destination(text, competitor):
    """Return explicit switch wording only when its destination is this term."""
    for prefix_pattern in _SWITCH_PREFIXES:
        for prefix in prefix_pattern.finditer(text):
            target = text[prefix.end():]
            leading = len(target) - len(target.lstrip())
            target = target.lstrip()
            match = _term_matches(target, competitor)
            if match and match[0].start() == 0:
                return prefix.start(), prefix.end() + leading + match[0].end()
    return None


def get_competitor_intelligence(project_id):
    entity = ProjectEntity.query.filter_by(project_id=project_id).first()
    competitors = list(entity.competitor_keywords or []) if entity else []
    reviews = Review.query.filter_by(project_id=project_id).filter(
        Review.deleted_at.is_(None), Review.is_spam.is_(False), Review.is_duplicate.is_(False)
    ).order_by(Review.created_at.desc()).limit(5000).all()
    items = []
    for review in reviews:
        text = review.text or ""
        for competitor in competitors:
            mentions = _term_matches(text, competitor)
            if not mentions:
                continue
            evidence = [{"text": mention.group(0), "sourceSpan": list(mention.span())}
                        for mention in mentions]
            switching_evidence = []
            reason = None
            for mention in mentions:
                mention_start, mention_end = mention.span()
                sent_start, sent_end = next(
                    ((start, end) for start, end in _sentences(text)
                     if start <= mention_start < end),
                    (mention_start, mention_end),
                )
                switching = _switching_destination(text[sent_start:sent_end], competitor)
                if switching:
                    switch_start = sent_start + switching[0]
                    switch_end = sent_start + switching[1]
                    switching_evidence.append({"text": text[switch_start:switch_end],
                                               "sourceSpan": [switch_start, switch_end]})
                    reason_match = _REASON.search(text[sent_start:sent_end])
                    if reason_match and reason is None:
                        reason_start = sent_start + reason_match.start(1)
                        reason_end = sent_start + reason_match.end(1)
                        reason = {"text": text[reason_start:reason_end].strip(),
                                  "sourceSpan": [reason_start, reason_end]}
            items.append({
                    "reviewId": str(review.id),
                    "competitor": competitor,
                    "switchingIntent": bool(switching_evidence),
                    "reason": reason,
                    "evidence": evidence,
                    "switchingEvidence": switching_evidence,
                    "source": review.source,
                    "origin": {
                        "type": "data_source" if review.data_source_id else "dataset",
                        "id": str(review.data_source_id or review.dataset_id),
                    },
                    "sentiment": (
                        review.sentiment_result.sentiment_label
                        if review.sentiment_result else None
                    ),
                })
    items.sort(key=lambda item: (not item["switchingIntent"], item["competitor"].casefold(), item["reviewId"]))
    result_limit = 500
    return {
        "items": items[:result_limit],
        "summary": {
            "mentions": len(items),
            "switchingIntent": sum(1 for item in items if item["switchingIntent"]),
            "competitors": len({item["competitor"].casefold() for item in items}),
            "reviewsScanned": len(reviews),
        },
        "truncated": len(items) > result_limit,
        "resultLimit": result_limit,
        "limitations": [
            "Only configured competitor phrases are matched.",
            "Switching intent is a deterministic phrase signal, not a verified customer decision.",
            "Reasons are quoted text following because, since, or as; they are not causal validation.",
            "At most 5,000 eligible project reviews are scanned.",
            "At most 500 review/competitor evidence records are returned.",
        ],
    }
