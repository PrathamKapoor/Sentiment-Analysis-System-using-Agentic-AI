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
"""
import re

from app.services.aspect_config import ASPECT_SYNONYMS
from app.services.sentiment_analyzer import get_analyzer

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text):
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]
    return sentences or ([text.strip()] if text and text.strip() else [])


def _surface_forms_by_length():
    # Longer phrases first, so "battery life" matches before the shorter "battery".
    return sorted(ASPECT_SYNONYMS.keys(), key=len, reverse=True)


class AspectAnalyzer:
    def __init__(self):
        self._sentiment = get_analyzer()
        self._surface_forms = _surface_forms_by_length()

    def extract_aspects(self, text):
        """Returns an ordered list of unique canonical aspect names found in text."""
        if not text:
            return []
        lowered = text.lower()
        found = []
        seen = set()
        for surface in self._surface_forms:
            pattern = r"\b" + re.escape(surface) + r"\b"
            if re.search(pattern, lowered):
                canonical = ASPECT_SYNONYMS[surface]
                if canonical not in seen:
                    seen.add(canonical)
                    found.append(canonical)
        return found

    def local_context(self, text, aspect):
        """The sentence(s) mentioning `aspect` within `text` (no sentiment call)."""
        sentences = _split_sentences(text)
        surfaces = [s for s, canonical in ASPECT_SYNONYMS.items() if canonical == aspect]

        matching_sentences = [
            sentence for sentence in sentences
            if any(re.search(r"\b" + re.escape(s) + r"\b", sentence.lower()) for s in surfaces)
        ]
        return " ".join(matching_sentences).strip() if matching_sentences else (text or "").strip()

    def analyse_aspect_sentiment(self, text, aspect):
        """Local-context sentiment for one aspect within the given text."""
        local_context = self.local_context(text, aspect)
        result = self._sentiment.analyze(local_context)
        return {
            "aspect": aspect,
            "label": result["label"],
            "confidence_score": result["confidence_score"],
            "evidence_text": local_context.strip(),
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
