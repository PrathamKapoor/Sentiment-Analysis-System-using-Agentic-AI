"""Sentiment evaluation service.

Evaluates the project's own VADER-based sentiment model against a small
labelled benchmark fixture shipped with the repository. No large dataset,
no model download, no GPU, no external API. All data is read from a CSV
fixture checked in at ``backend/fixtures/sentiment_benchmark.csv``.

The benchmark is 70 rows: 26 positive, 22 neutral, 22 negative
(synthetic, hand-labelled; VADER's own documented accuracy ceiling of
~65-80% on short-of-text data means this is a conservative fixture). The
panel in the frontend must carry the disclaimer that benchmark accuracy
is a controlled diagnostic, not a claim about universal performance.

Public entry point: ``evaluate_benchmark()`` returns a fully reproducible
``BenchmarkResult``. The caller may supply a ``max_rows`` cap if the
fixture is ever enlarged; currently the whole file is used.
"""
from __future__ import annotations

import csv
import hashlib
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from app.services.sentiment_analyzer import MODEL_NAME, MODEL_VERSION, get_analyzer

_BENCHMARK_CSV = os.path.join(
    os.path.dirname(__file__), "..", "..", "fixtures", "sentiment_benchmark.csv"
)
_BENCHMARK_ID = "sentiment_benchmark_v1"
_BENCHMARK_VERSION = "1.0.0"

_POSITIVE_THRESHOLD = 0.05
_NEGATIVE_THRESHOLD = -0.05


def _confidence_for(label, pos, neg, neu):
    return {"positive": pos, "negative": neg, "neutral": neu}.get(label, 0.0)


def _normalize(s):
    return s.strip().lower() if isinstance(s, str) else str(s).strip().lower()


_SUPPORTED_LABELS = {"positive", "negative", "neutral"}


def _analyze_and_label(text):
    analyzer = get_analyzer()
    result = analyzer.analyze(text or "")
    return result["label"], result

def _load_benchmark_rows():
    path = os.path.normpath(_BENCHMARK_CSV)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Benchmark fixture not found: {path}. "
            "Expected a CSV with columns text,label at backend/fixtures/sentiment_benchmark.csv"
        )
    rows: List[Tuple[str, str]] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("Benchmark fixture has no header row")
        lowercols = {k.lower(): k for k in reader.fieldnames}
        text_col = lowercols.get("text")
        label_col = lowercols.get("label")
        if text_col is None or label_col is None:
            raise ValueError("Benchmark fixture must have columns 'text' and 'label'")
        for raw in reader:
            text_val = (raw.get(text_col) or "").strip()
            label_val = _normalize(raw.get(label_col))
            if not text_val:
                continue
            if not label_val or label_val not in _SUPPORTED_LABELS:
                raise ValueError(
                    f"Unsupported benchmark label '{label_val}' — "
                    f"supported are {', '.join(sorted(_SUPPORTED_LABELS))}"
                )
            rows.append((text_val, label_val))
    return rows


def _per_class_metrics(labels, preds, confusion, classes):
    """Return per-class precision/recall/F1 and support."""
    out = {}
    for cls in classes:
        tp = confusion[cls][cls]
        fp = sum(confusion[other][cls] for other in classes if other != cls)
        fn = sum(confusion[cls][other] for other in classes if other != cls)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        support = sum(1 for l in labels if l == cls)
        out[cls] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": int(support),
        }
    return out


def _macro_avg(per_class, key):
    vals = [per_class[cls][key] for cls in per_class]
    return round(sum(vals) / len(vals), 4) if vals else 0.0


def evaluate_benchmark() -> Dict:
    rows = _load_benchmark_rows()
    if not rows:
        raise ValueError("Benchmark fixture is empty")

    text_list = [text for text, _ in rows]
    true_labels = [label for _, label in rows]

    analyzer = get_analyzer()
    predictions: List[str] = []
    scores: List[Dict] = []
    for text in text_list:
        result = analyzer.analyze(text)
        predictions.append(result["label"])
        scores.append(result)

    n = len(rows)
    correct = sum(1 for t, p in zip(true_labels, predictions) if t == p)
    accuracy = round(correct / n, 4) if n else 0.0

    classes = ("positive", "negative", "neutral")
    cm = {t: {p: 0 for p in classes} for t in classes}
    for t, p in zip(true_labels, predictions):
        cm[t][p] += 1

    per_class = _per_class_metrics(true_labels, predictions, cm, classes)

    macro_precision = _macro_avg(per_class, "precision")
    macro_recall = _macro_avg(per_class, "recall")
    macro_f1 = _macro_avg(per_class, "f1")

    fiction = os.path.join(os.path.dirname(os.path.abspath(_BENCHMARK_CSV)), "..", "fixtures")
    try:
        with open(os.path.normpath(_BENCHMARK_CSV), "rb") as fh:
            sha = hashlib.sha256(fh.read()).hexdigest()[:12]
    except Exception:
        sha = None

    return {
        "benchmarkId": _BENCHMARK_ID,
        "benchmarkVersion": _BENCHMARK_VERSION,
        "datasetSha256Prefix": sha,
        "model": {"name": MODEL_NAME, "version": MODEL_VERSION},
        "sampleCount": n,
        "metrics": {
            "accuracy": accuracy,
            "macroPrecision": macro_precision,
            "macroRecall": macro_recall,
            "macroF1": macro_f1,
            "perClass": per_class,
            "correct": int(correct),
            "total": int(n),
        },
        "confusionMatrix": cm,
        "evaluatedAt": datetime.now(timezone.utc).isoformat(),
        "classCounts": dict(Counter(true_labels)),
        "labelSet": list(classes),
    }


def benchmark_feature_texts():
    """Return the raw text strings of the benchmark fixture (for the CLI)."""
    return [text for text, _ in _load_benchmark_rows()]
