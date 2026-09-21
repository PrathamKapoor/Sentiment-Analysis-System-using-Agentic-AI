"""Aspect extraction + local aspect-sentiment, baseline suitable for a
student project and viva: no external paid LLM, no spaCy/model-download
dependency (kept deliberately lightweight per the Phase 4 brief's own
"if spaCy would add unnecessary complexity" fallback clause).

extract_aspects(): a configured aspect dictionary (app/services/aspect_config.py)
matched against the review text via word/phrase search — this is the
"configured aspect dictionary" fallback approach, not noun-phrase POS tagging.
Every match is directly explainable: "this review contains the phrase
'battery life', which maps to the 'battery' aspect."

analyse_aspect_sentiment(): sentiment is computed on the *sentence* containing
the aspect mention (via the Phase 3 VADER analyzer), not the whole review —
so "The design looks great. The battery is terrible." correctly splits into
design=positive, battery=negative rather than both getting the review's
mixed/averaged score.

Known limitation: splitting is sentence-level (on . ! ?), not clause-level —
"The design looks great but the battery is terrible" (one sentence, joined by
"but") gets the *same* local context, and therefore the same sentiment, for
both aspects. Clause-level splitting (on conjunctions like "but"/"however")
would fix this but adds real ambiguity of its own; left as a documented
baseline limitation rather than over-engineered. See the README.

Negation handling
-----------------
aspect_sentiment for a review with "not"/"never" is also deterministically
derived from VADER's own cue handling. There is no extra correction layer —
any such correction was explicitly removed in Phase 10 after empirical
testing showed both false positives ("The battery never fails.") and
redundant doubling of VADER's own handling. The result exposes VADER's
compound score directly so callers can see the underlying signal.
"""
import re

from app.services.aspect_config import ASPECT_SYNONYMS
from app.services.sentiment_analyzer import get_analyzer

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

def _split_sentences(text):
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]
    return sentences or ([text.strip()] if text and text.strip() else [])


def _surface_forms_by_length(synonym_map=None):
    """Longer phrases first, so 'battery life' matches before 'battery'."""
    src = synonym_map if synonym_map is not None else ASPECT_SYNONYMS
    return sorted(src.keys(), key=len, reverse=True)


def _effective_synonyms(project_id=None, extra_synonyms=None):
    """Resolve the effective synonym map for a project.

    ``extra_synonyms`` takes priority (callers that already fetched
    per-project rows can pass the merged map). If a ``project_id`` is
    supplied without ``extra_synonyms``, the per-project vocab is
    fetched here. If neither is supplied, the global seed is used.
    """
    if extra_synonyms is not None:
        return extra_synonyms
    if project_id is not None:
        try:
            from app.services.project_aspect_vocabulary_service import effective_vocab_for_project
            return effective_vocab_for_project(project_id)
        except Exception:
            pass
    return ASPECT_SYNONYMS


def _truncate_evidence(text, max_chars=300):
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 30].rstrip() + " ... [truncated]"


class AspectAnalyzer:
    def __init__(self, synonyms=None):
        self._sentiment = get_analyzer()
        self._synonyms = synonyms if synonyms is not None else ASPECT_SYNONYMS
        self._surface_forms = _surface_forms_by_length(self._synonyms)

    def with_vocabulary(self, synonym_map):
        """Return a new analyzer instance using ``synonym_map``."""
        return AspectAnalyzer(synonyms=synonym_map)

    def for_project(self, project_id):
        """Return a new analyzer instance using the effective vocabulary
        for the given project (project rows + global seed fallback).
        """
        return AspectAnalyzer(synonyms=_effective_synonyms(project_id=project_id))

    def extract_aspects(self, text, synonyms=None):
        """Returns an ordered list of unique canonical aspect names found in text."""
        syn = synonyms if synonyms is not None else self._synonyms
        surfaces = _surface_forms_by_length(syn)
        if not text:
            return []
        lowered = text.lower()
        found = []
        seen = set()
        for surface in surfaces:
            pattern = r"\b" + re.escape(surface) + r"\b"
            if re.search(pattern, lowered):
                canonical = syn[surface]
                if canonical not in seen:
                    seen.add(canonical)
                    found.append(canonical)
        return found

    def local_context(self, text, aspect, synonyms=None):
        """The sentence(s) mentioning ``aspect`` within ``text`` (no sentiment call)."""
        syn = synonyms if synonyms is not None else self._synonyms
        sentences = _split_sentences(text)
        surfaces = [s for s, canonical in syn.items() if canonical == aspect]

        matching_sentences = [
            sentence for sentence in sentences
            if any(re.search(r"\b" + re.escape(s) + r"\b", sentence.lower()) for s in surfaces)
        ]
        return " ".join(matching_sentences).strip() if matching_sentences else (text or "").strip()

    def analyse_aspect_sentiment(self, text, aspect):
        """Local-context sentiment for one aspect within the given text.

        Pure VADER over the sentence containing the aspect. No
        post-correction — Phase 10 audit removed the negation-hint flip
        because it produced obvious false positives on constructions
        like "The battery never fails." VADER's own negation handling
        is the single source of truth.
        """
        local_context = self.local_context(text, aspect)
        result = self._sentiment.analyze(local_context)
        compound = float(result.get("compound", 0.0) or 0.0)

        return {
            "aspect": aspect,
            "label": result["label"],
            "confidence_score": float(result["confidence_score"]),
            "compound": compound,
            "evidence_text": _truncate_evidence(local_context),
        }

    def analyse_review(self, text):
        aspects = self.extract_aspects(text)
        return [self.analyse_aspect_sentiment(text, aspect) for aspect in aspects]

    def analyse_batch(self, texts):
        return [self.analyse_review(t) for t in texts]


_default_analyzer = None


def get_aspect_analyzer():
    global _default_analyzer
    if _default_analyzer is None:
        _default_analyzer = AspectAnalyzer()
    return _default_analyzer
