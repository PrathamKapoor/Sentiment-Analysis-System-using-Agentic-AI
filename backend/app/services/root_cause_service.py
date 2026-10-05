"""Evidence-layered issue analysis; generated hypotheses are not causal findings."""
import re

from app.models import Review
from app.services.temporal_intelligence_service import _window_counts, _signals

_VERSION_RE = re.compile(r"\b(?:version|release|v)\s*([0-9]+(?:\.[0-9]+){1,3})\b", re.I)


def get_root_cause_evidence(project_id, *, days=7, baseline_days=7):
    baseline, current, window = _window_counts(project_id, days, baseline_days)
    before, after = _signals(baseline), _signals(current)
    claims = []
    categories = sorted(key for key in set(before) | set(after) if not key.startswith("ASPECT:"))
    for category in categories:
        old = before.get(category, {}).get("count", 0)
        new = after.get(category, {}).get("count", 0)
        if new < 3:
            continue
        evidence = after[category]["evidence"]
        claims.append({"type": "FACT", "claim": f"{new} eligible dated reviews matched the deterministic {category} phrase rules in the comparison period.",
            "evidenceIds": evidence, "method": "deterministic_phrase_count_v1"})
        if old > 0 and (new / max(days, 1)) / (old / max(baseline_days, 1)) >= 1.5:
            claims.append({"type": "OBSERVATION", "claim": f"{category} mentions increased from {old} in the baseline window to {new} in the comparison window.",
                "evidenceIds": evidence, "method": "adjacent_period_rate_comparison_v1"})
            ids = set(evidence)
            current_rows = Review.query.filter(Review.id.in_(ids)).all() if ids else []
            versions = {}
            for review in current_rows:
                for match in _VERSION_RE.finditer(review.text or ""):
                    versions.setdefault(match.group(1), []).append(str(review.id))
            for version, version_ids in versions.items():
                if len(version_ids) >= 2:
                    claims.append({"type": "CORRELATION", "claim": f"The {category} increase overlaps with {len(version_ids)} reports mentioning version {version}; this is temporal/textual overlap only.",
                        "evidenceIds": sorted(set(version_ids)), "method": "co_mentioned_version_v1"})
                    claims.append({"type": "HYPOTHESIS", "claim": f"Version {version} may be associated with the increase in {category} reports; the reviews do not establish causation.",
                        "evidenceIds": sorted(set(version_ids)), "method": "conservative_template_hypothesis_v1"})
                    claims.append({"type": "RECOMMENDATION", "claim": f"Compare product telemetry and release history for version {version} against the {category} evidence.",
                        "evidenceIds": sorted(set(version_ids)), "method": "evidence_linked_review_action_v1"})
                    break
    return {"comparison": window, "claims": claims,
            "limitations": ["This service does not infer causation.", "FACT counts refer to phrase-rule matches, not independently verified events.",
                            "Version overlap is correlation only and depends on text explicitly naming a version."]}
