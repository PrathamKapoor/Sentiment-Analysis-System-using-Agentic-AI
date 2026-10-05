from app.services.project_keyword_matching import evaluate_record_keywords


def test_inclusion_terms_match_any_configured_term_case_insensitively():
    decision = evaluate_record_keywords(
        "The CAMERA is sharp", source_keywords=["battery"],
        entity={"includeKeywords": ["camera", "display"]},
    )
    assert decision["included"] is True
    assert decision["matchedIncludeKeywords"] == ["camera"]


def test_exclusion_terms_take_precedence_over_inclusion_terms():
    decision = evaluate_record_keywords(
        "Great camera but this is a case review", source_keywords=["camera"],
        entity={"excludeKeywords": ["case"]},
    )
    assert decision["included"] is False
    assert decision["excludedBy"] == ["case"]


def test_no_configured_inclusion_terms_keeps_record_and_collects_analysis_cues():
    decision = evaluate_record_keywords(
        "Privacy controls are confusing", source_keywords=[],
        entity={"securityKeywords": ["privacy"], "competitorKeywords": ["Pixel"]},
    )
    assert decision["included"] is True
    assert decision["matchedSecurityKeywords"] == ["privacy"]
    assert decision["matchedCompetitorKeywords"] == []


def test_keyword_match_uses_phrase_boundaries():
    decision = evaluate_record_keywords(
        "I like the batterycase", source_keywords=["battery"], entity={},
    )
    assert decision["included"] is False
