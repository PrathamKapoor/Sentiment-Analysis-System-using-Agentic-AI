"""Deterministic, bounded matching for configured project/source keyword terms."""
import re


def _terms(values):
    return [value.strip() for value in (values or []) if isinstance(value, str) and value.strip()]


def _matches(text, terms):
    folded = text.casefold()
    return [term for term in terms if re.search(
        rf"(?<![\w]){re.escape(term.casefold())}(?![\w])", folded
    )]


def evaluate_record_keywords(text, source_keywords=None, entity=None):
    """Return inclusion and annotation matches without modifying source text.

    Configured source/project inclusion terms use any-match semantics. Exclusion
    terms always win. Security, competitor, and custom terms annotate records;
    they never filter them out.
    """
    entity = entity or {}
    source_terms = _terms(source_keywords)
    project_terms = _terms(entity.get("includeKeywords"))
    excluded = _matches(text, _terms(entity.get("excludeKeywords")))
    matched_source = _matches(text, source_terms)
    matched_project = _matches(text, project_terms)
    inclusion_configured = bool(source_terms or project_terms)
    return {
        "included": not excluded and (not inclusion_configured or bool(matched_source or matched_project)),
        "matchedIncludeKeywords": list(dict.fromkeys(matched_source + matched_project)),
        "matchedSourceKeywords": matched_source,
        "matchedProjectKeywords": matched_project,
        "excludedBy": excluded,
        "matchedSecurityKeywords": _matches(text, _terms(entity.get("securityKeywords"))),
        "matchedCompetitorKeywords": _matches(text, _terms(entity.get("competitorKeywords"))),
        "matchedCustomKeywords": _matches(text, _terms(entity.get("customKeywords"))),
    }
