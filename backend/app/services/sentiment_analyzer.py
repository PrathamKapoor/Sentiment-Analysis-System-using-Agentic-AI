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
"""
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

MODEL_NAME = "vader"
MODEL_VERSION = "3.3.2"

POSITIVE_THRESHOLD = 0.05
NEGATIVE_THRESHOLD = -0.05


class SentimentAnalyzer:
    def analyze(self, text):
        raise NotImplementedError

    def analyze_batch(self, texts):
        return [self.analyze(t) for t in texts]


class VaderSentimentAnalyzer(SentimentAnalyzer):
    def __init__(self):
        self._vader = SentimentIntensityAnalyzer()

    def analyze(self, text):
        scores = self._vader.polarity_scores(text or "")
        compound = scores["compound"]

        if compound >= POSITIVE_THRESHOLD:
            label = "positive"
        elif compound <= NEGATIVE_THRESHOLD:
            label = "negative"
        else:
            label = "neutral"

        positive_score = round(scores["pos"], 4)
        negative_score = round(scores["neg"], 4)
        neutral_score = round(scores["neu"], 4)
        confidence_score = {
            "positive": positive_score,
            "negative": negative_score,
            "neutral": neutral_score,
        }[label]

        return {
            "label": label,
            "positive_score": positive_score,
            "negative_score": negative_score,
            "neutral_score": neutral_score,
            "confidence_score": confidence_score,
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
        }

    def analyze_batch(self, texts):
        return [self.analyze(t) for t in texts]


_default_analyzer = None


def get_analyzer():
    global _default_analyzer
    if _default_analyzer is None:
        _default_analyzer = VaderSentimentAnalyzer()
    return _default_analyzer
