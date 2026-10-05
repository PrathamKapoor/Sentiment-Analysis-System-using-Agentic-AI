"""Evidence-first deterministic security signal extraction.

These rules identify customer-reported signals, not verified incidents.
"""
import re
import hashlib
from urllib.parse import urlsplit, urlunsplit

from app.extensions import db
from app.models import Review, SecurityFinding


_SIGNALS = (
    ("ACCOUNT_COMPROMISE", "HIGH", r"\b(?:account was taken over|account takeover|unauthori[sz]ed (?:login|access)|someone logged in without permission)\b"),
    ("PERSONAL_DATA_EXPOSURE", "HIGH", r"\b(?:exposed my personal data|leaked my (?:personal )?data|other users can see my data|data breach)\b"),
    ("PAYMENT_FRAUD", "HIGH", r"\b(?:fraudulent charge|unauthori[sz]ed charge|payment fraud|charged without (?:my )?authori[sz]ation)\b"),
    ("PHISHING_OR_IMPERSONATION", "MEDIUM", r"\b(?:phishing (?:email|message|link)|impersonating (?:the )?(?:company|support)|fake support account)\b"),
    ("AUTHENTICATION_FAILURE", "MEDIUM", r"\b(?:mfa code (?:never arrived|does not work)|locked out after password reset|cannot reset my password)\b"),
    ("MALWARE_REPORT", "HIGH", r"\b(?:installed spyware|ransomware encrypted|downloaded malware|malware infected)\b"),
    ("APPLICATION_VULNERABILITY_REPORT", "MEDIUM", r"\b(?:sql injection|cross[- ]site scripting|exposed api key|insecure direct object reference)\b"),
    ("TLS_CERTIFICATE_FAILURE", "LOW", r"\b(?:expired tls certificate|invalid ssl certificate|certificate warning)\b"),
)

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.I)
_IP_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_HASH_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", re.I)
_DOMAIN_RE = re.compile(r"(?<![\w.-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(?![\w.-])", re.I)


def _safe_url(value):
    value = value.rstrip(".,;:!?)]}>")
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        host = parts.hostname.encode("idna").decode("ascii").lower()
        if parts.port:
            host += f":{parts.port}"
        return urlunsplit((parts.scheme.lower(), host, parts.path[:512], "", ""))
    except (ValueError, UnicodeError):
        return None


def extract_security_indicators(text):
    """Extract syntactically supported indicators as observations only.

    This function performs no reputation lookups and never labels an indicator
    malicious or verified. URL query strings and fragments are discarded.
    """
    if not isinstance(text, str) or not text:
        return []
    found, occupied = [], []

    def add(kind, value, start, end, evidence_text=None):
        key = (kind, value.casefold())
        if any((item["type"], item["value"].casefold()) == key for item in found):
            return
        found.append({"type": kind, "value": value, "status": "OBSERVED", "confidence": None,
                      "evidence": evidence_text or text[start:end], "sourceSpan": [start, end],
                      "method": "strict_syntax_extraction_v1"})

    for match in _URL_RE.finditer(text):
        url = _safe_url(match.group(0))
        if url:
            add("URL", url, match.start(), match.end(), evidence_text=url)
            occupied.append((match.start(), match.end()))
            host = urlsplit(url).hostname
            if host and "." in host:
                add("DOMAIN", host, match.start(), match.end(), evidence_text=host)
    for match in _CVE_RE.finditer(text):
        add("CVE", match.group(0).upper(), match.start(), match.end())
    for match in _IP_RE.finditer(text):
        try:
            parts = [int(part) for part in match.group(0).split(".")]
            if all(0 <= part <= 255 for part in parts):
                add("IP", match.group(0), match.start(), match.end())
        except ValueError:
            pass
    for match in _HASH_RE.finditer(text):
        add("HASH_SHA256", match.group(0).lower(), match.start(), match.end())
    for match in _DOMAIN_RE.finditer(text):
        if any(match.start() < end and match.end() > start for start, end in occupied):
            continue
        add("DOMAIN", match.group(0).lower(), match.start(), match.end())
    return found


_CATEGORY_BY_FINDING = {
    "ACCOUNT_COMPROMISE": "ACCOUNT_SECURITY",
    "PERSONAL_DATA_EXPOSURE": "DATA_EXPOSURE",
    "PAYMENT_FRAUD": "PAYMENT_SECURITY",
    "PHISHING_OR_IMPERSONATION": "PHISHING",
    "AUTHENTICATION_FAILURE": "AUTHENTICATION",
    "MALWARE_REPORT": "MALWARE",
    "APPLICATION_VULNERABILITY_REPORT": "APPLICATION_SECURITY",
    "TLS_CERTIFICATE_FAILURE": "NETWORK_SECURITY",
}


def extract_security_signals(text):
    if not isinstance(text, str) or not text:
        return []
    findings = []
    for finding_type, severity, pattern in _SIGNALS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        findings.append({
            "findingType": finding_type,
            "category": _CATEGORY_BY_FINDING.get(finding_type, "OTHER"),
            "severity": severity,
            # Exact phrase match is evidence for a reported signal, not a
            # calibrated probability that the underlying event occurred.
            "confidence": None,
            "evidence": [{"text": match.group(0), "sourceSpan": [match.start(), match.end()]}],
            "indicators": extract_security_indicators(text),
            "classificationMethod": "deterministic_phrase_v1",
            "status": "needs_review",
        })
    return findings


def analyze_project_security_signals(project):
    """Reconcile deterministic signals against current eligible project reviews."""
    existing = {
        (str(f.review_id), f.finding_type): f
        for f in SecurityFinding.query.filter_by(project_id=project.id).all()
    }
    existing_by_review = {}
    for finding in existing.values():
        existing_by_review.setdefault(str(finding.review_id), []).append(finding)
    created = updated = stale = 0
    for review in Review.query.filter_by(project_id=project.id).yield_per(200):
        key_review_id = str(review.id)
        review_text_sha256 = hashlib.sha256((review.text or "").encode("utf-8")).hexdigest()
        candidates = (
            extract_security_signals(review.text)
            if review.deleted_at is None and not review.is_spam and not review.is_duplicate
            else []
        )
        current_types = set()
        for candidate in candidates:
            finding_type = candidate["findingType"]
            current_types.add(finding_type)
            key = (key_review_id, finding_type)
            finding = existing.get(key)
            if finding is None:
                finding = SecurityFinding(
                    organisation_id=project.organisation_id, project_id=project.id,
                    review_id=review.id, finding_type=finding_type,
                    severity=candidate["severity"], confidence=candidate["confidence"],
                    evidence=candidate["evidence"], indicators=candidate["indicators"],
                    classification_method=candidate["classificationMethod"],
                    review_text_sha256=review_text_sha256, status="needs_review",
                )
                db.session.add(finding)
                existing[key] = finding
                created += 1
                continue

            changed = any((
                finding.severity != candidate["severity"],
                finding.evidence != candidate["evidence"],
                finding.indicators != candidate["indicators"],
                finding.classification_method != candidate["classificationMethod"],
                finding.review_text_sha256 != review_text_sha256,
            ))
            if changed or finding.status == "stale":
                finding.severity = candidate["severity"]
                finding.confidence = candidate["confidence"]
                finding.evidence = candidate["evidence"]
                finding.indicators = candidate["indicators"]
                finding.classification_method = candidate["classificationMethod"]
                finding.review_text_sha256 = review_text_sha256
                # A previous human decision applied to old evidence and must
                # be reviewed again when the source text has changed.
                finding.status = "needs_review"
                finding.reviewed_by = None
                finding.reviewed_at = None
                finding.analyst_notes = None
                updated += 1

        for finding in existing_by_review.get(key_review_id, []):
            if finding.finding_type not in current_types and finding.status != "stale":
                # Keep the original evidence for auditability, but make clear
                # that it no longer matches current eligible review text.
                finding.status = "stale"
                stale += 1

    db.session.flush()
    return {"created": created, "updated": updated, "stale": stale, "total": len(existing)}


def get_project_security_indicators(project_id):
    """Return persisted indicator observations linked to current findings."""
    from app.models import Review
    findings = SecurityFinding.query.filter_by(project_id=project_id).filter(
        SecurityFinding.status.notin_(("stale", "dismissed"))
    ).all()
    result, seen = [], set()
    for finding in findings:
        review = Review.query.filter_by(id=finding.review_id, project_id=project_id).first()
        if review is None or review.deleted_at is not None or review.is_spam or review.is_duplicate:
            continue
        for indicator in finding.indicators or []:
            key = (indicator.get("type"), indicator.get("value"), str(review.id))
            if key in seen:
                continue
            seen.add(key)
            result.append({**indicator, "reviewId": str(review.id), "findingId": str(finding.id),
                           "source": review.source, "findingType": finding.finding_type,
                           "category": _CATEGORY_BY_FINDING.get(finding.finding_type, "OTHER")})
    return result[:2000]


def correlate_security_signals(project_id):
    """Correlate repeated indicator observations; customer reports never confirm incidents."""
    observations = get_project_security_indicators(project_id)
    groups = {}
    for item in observations:
        if item.get("status") == "VERIFIED":
            continue
        key = (item.get("type"), (item.get("value") or "").casefold())
        groups.setdefault(key, []).append(item)
    correlated = []
    for (kind, value), rows in groups.items():
        evidence_ids = sorted({row["reviewId"] for row in rows})
        sources = sorted({row.get("source") or "unknown" for row in rows})
        if len(evidence_ids) < 2:
            continue
        correlated.append({"indicatorType": kind, "indicator": value,
            "status": "POSSIBLE_INCIDENT" if len(sources) >= 2 else "OBSERVED_PATTERN",
            "evidenceCount": len(evidence_ids), "evidenceIds": evidence_ids,
            "sources": sources, "verification": "Not independently verified; customer-reported evidence only."})
    return sorted(correlated, key=lambda row: (-row["evidenceCount"], row["indicatorType"], row["indicator"]))[:200]
