"""Sentiment analysis engine, kept behind a small interface so the model
backing it can be swapped later without touching callers.

Phase 3 baseline: VADER (rule-based, lexicon + heuristics), via the
`vaderSentiment` package — no network calls, no paid APIs, deterministic.

Thresholds (VADER's own documented convention, used as-is):
    compound >=  0.05  -> positive
    compound <= -0.05  -> negative
    otherwise          -> neutral

confidence_score is defined as the score of the winning label (whichever of
positive_score/negative_score/neutral_score corresponds to the chosen label)
— not a separate calibrated probability. This is a real limitation of a
lexicon-based baseline: VADER does not produce a true confidence estimate.
See the README's "Limitations" section.

Explainability: ``analyze`` now also returns a ``vader_breakdown`` block
that lists every whitespace-delimited token together with the raw VADER
valence for the lowercased form. This is what the actual VADER lexicon
says about each token, not a post-hoc narrative. A ``contributingTerms``
list highlights the strongest tokens pointing in the winning-label
direction. The breakdown never claims a review is "objectively" anything —
it is a lexicon lookup, period.
"""
import os
import re
import string

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

MODEL_NAME = "vader"
MODEL_VERSION = "3.3.2"

POSITIVE_THRESHOLD = 0.05
NEGATIVE_THRESHOLD = -0.05

_TOKEN_RE = re.compile(r"\S+")
_TOP_N_CONTRIBUTORS = 8


class SentimentAnalyzer:
    def analyze(self, text):
        raise NotImplementedError

    def analyze_batch(self, texts):
        return [self.analyze(t) for t in texts]


class VaderSentimentAnalyzer(SentimentAnalyzer):
    def __init__(self):
        self._vader = SentimentIntensityAnalyzer()
        self._lexicon = self._vader.lexicon

    def _label_from_compound(self, compound):
        if compound >= POSITIVE_THRESHOLD:
            return "positive"
        if compound <= NEGATIVE_THRESHOLD:
            return "negative"
        return "neutral"

    def _token_breakdown(self, text):
        """Per-token lexicon lookups.

        VADER's full ``score_valence`` applies a richer pipeline
        (capitalisation, negation, booster words, emoticons). This
        function does *not* re-run that pipeline. It lowercases each
        whitespace-delimited token, strips edge punctuation, and
        reports the raw lexicon valence for the lowercased form. This
        is an explanation surface for the lexicon, not a re-implementation
        of VADER's score composition. Tokens not in the lexicon return
        ``valence=0.0, matched=False``.
        """
        if not text:
            return []
        breakdown = []
        for token in _TOKEN_RE.findall(text):
            lowered = token.lower().strip(string.punctuation)
            if not lowered:
                continue
            valence = float(self._lexicon.get(lowered, 0.0))
            breakdown.append({
                "token": token,
                "lowered": lowered,
                "valence": round(valence, 4),
                "matched": valence != 0.0,
            })
        return breakdown

    def _contributing_terms(self, breakdown, label):
        if label not in ("positive", "negative") or not breakdown:
            return {"positive": [], "negative": []}
        sign = -1.0 if label == "negative" else 1.0
        scored = [
            item for item in breakdown
            if item["matched"] and (item["valence"] * sign) > 0
        ]
        scored.sort(key=lambda x: abs(x["valence"]), reverse=True)
        top = [
            {"token": item["token"], "valence": item["valence"]}
            for item in scored[:_TOP_N_CONTRIBUTORS]
        ]
        if label == "negative":
            return {"positive": [], "negative": top}
        return {"positive": top, "negative": []}

    def analyze(self, text):
        scores = self._vader.polarity_scores(text or "")
        compound = float(scores["compound"])
        label = self._label_from_compound(compound)

        positive_score = round(scores["pos"], 4)
        negative_score = round(scores["neg"], 4)
        neutral_score = round(scores["neu"], 4)
        confidence_score = {
            "positive": positive_score,
            "negative": negative_score,
            "neutral": neutral_score,
        }[label]

        breakdown = self._token_breakdown(text or "")
        contributing = self._contributing_terms(breakdown, label)

        return {
            "label": label,
            "compound": round(compound, 4),
            "positive_score": positive_score,
            "negative_score": negative_score,
            "neutral_score": neutral_score,
            "confidence_score": confidence_score,
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "vader_breakdown": {
                "tokens": breakdown,
                "contributingTerms": contributing,
            },
        }

    def analyze_batch(self, texts):
        return [self.analyze(t) for t in texts]


_default_analyzer = None
_engine_name = None


def get_analyzer():
    """Return the process-wide sentiment analyzer instance.

    Selection is env-driven (``SENTIMENT_ENGINE``):
      - ``"vader"`` (default) — the original VaderSentimentAnalyzer
      - ``"stub"``              — a tiny built-in lexicon engine used
                                 for unit tests and offline smoke
                                 testing, no external dep

    The factory caches the instance for the lifetime of the process.
    Tests can call ``reset_analyzer_cache()`` to swap the engine.
    """
    global _default_analyzer, _engine_name
    if _default_analyzer is None:
        _default_analyzer = _build_default()
        _engine_name = os.environ.get("SENTIMENT_ENGINE", "vader").lower() or "vader"
    return _default_analyzer


def reset_analyzer_cache(analyzer=None, engine_name=None):
    """Used by tests and by the app factory when config changes."""
    global _default_analyzer, _engine_name
    _default_analyzer = analyzer
    _engine_name = engine_name


def current_engine_name() -> str:
    global _engine_name
    if _engine_name is None:
        get_analyzer()
    return _engine_name or "vader"


def _build_default():
    import os
    name = (os.environ.get("SENTIMENT_ENGINE") or "vader").lower()
    if name == "stub":
        return StubLexiconSentimentAnalyzer()
    if name and name != "vader":
        # Unknown engine name: fall back to VADER with a warning rather
        # than refusing to start.
        import logging
        logging.getLogger(__name__).warning(
            "Unknown SENTIMENT_ENGINE=%r; falling back to vader", name,
        )
    return VaderSentimentAnalyzer()


# --- Alternative engine (lightweight, no external dep, deterministic) ----

_STUB_LEXICON = {
    # small, hand-curated starter set. Not a replacement for VADER — a
    # demonstration that the analyzer interface is pluggable and that a
    # different engine produces a different breakdown. NOT for production.
    "good": 1.5, "great": 2.0, "excellent": 2.5, "amazing": 2.5,
    "love": 2.0, "loved": 2.0, "best": 2.0, "perfect": 2.5,
    "happy": 1.5, "fast": 1.0, "easy": 1.0, "helpful": 1.5,
    "friendly": 1.0, "beautiful": 1.8, "recommend": 1.5, "works": 0.5,
    "bad": -1.5, "terrible": -2.5, "awful": -2.0, "horrible": -2.0,
    "worst": -2.0, "hate": -2.0, "hated": -2.0, "broken": -1.5,
    "slow": -1.0, "difficult": -1.0, "rude": -1.5, "expensive": -0.5,
    "disappointed": -1.8, "useless": -2.0, "waste": -1.8, "fail": -1.5,
    "failed": -1.5, "crash": -1.5, "crashed": -1.5, "buggy": -1.5,
    "ok": 0.0, "okay": 0.0, "fine": 0.0, "average": 0.0,
}


class StubLexiconSentimentAnalyzer(SentimentAnalyzer):
    """A small, hand-curated lexicon engine used to demonstrate the
    pluggable analyzer interface. NOT a replacement for VADER. Always
    reports model_name ``"stub-lexicon"`` and version ``"1.0"`` so
    downstream code can recognise it.
    """

    def __init__(self):
        self._lex = dict(_STUB_LEXICON)
        self._pos_threshold = 0.05
        self._neg_threshold = -0.05

    def analyze(self, text):
        tokens = re.findall(r"[A-Za-z']+", (text or "").lower())
        breakdown = []
        for t in tokens:
            v = float(self._lex.get(t, 0.0))
            breakdown.append({"token": t, "lowered": t, "valence": round(v, 4), "matched": v != 0.0})
        total = sum(item["valence"] for item in breakdown)
        # Normalise roughly to [-1, 1] like VADER's compound.
        compound = max(-1.0, min(1.0, total / 3.0))
        label = "positive" if compound >= self._pos_threshold else "negative" if compound <= self._neg_threshold else "neutral"
        # Reuse VADER's threshold convention; confidence is a strength-of-signal value.
        confidence = min(1.0, abs(compound))
        # Top contributors in the label direction.
        sign = 1.0 if label == "positive" else -1.0 if label == "negative" else 0.0
        scored = [b for b in breakdown if (b["valence"] * sign) > 0]
        scored.sort(key=lambda x: abs(x["valence"]), reverse=True)
        contributing = {
            "positive": [{"token": b["token"], "valence": b["valence"]} for b in scored[:8]] if label == "positive" else [],
            "negative": [{"token": b["token"], "valence": b["valence"]} for b in scored[:8]] if label == "negative" else [],
        }
        return {
            "label": label,
            "compound": round(compound, 4),
            "positive_score": round(max(0.0, compound), 4),
            "negative_score": round(max(0.0, -compound), 4),
            "neutral_score": round(1.0 - abs(compound), 4),
            "confidence_score": round(confidence, 4),
            "model_name": "stub-lexicon",
            "model_version": "1.0",
            "vader_breakdown": {
                "tokens": breakdown,
                "contributingTerms": contributing,
            },
        }
