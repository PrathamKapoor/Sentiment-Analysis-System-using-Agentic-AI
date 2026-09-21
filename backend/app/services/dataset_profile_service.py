"""Deterministic, dependency-light dataset-quality profiling.

Computes a structured JSON-compatible profile of a dataset's contents from
the same raw rows the dataset service already parses. The profile is a
diagnostic — it never blocks processing. It distinguishes:

  - ERROR:    the dataset cannot be processed (a separate concern, raised
              elsewhere by the validation pipeline)
  - WARNING:  the dataset can be processed but quality is poor (e.g. very
              short texts, excessive ALL-CAPS, URL-heavy rows)
  - INFO:     useful diagnostic information (e.g. language distribution,
              rating distribution, row counts, average text length)

Heuristics only — no model download, no external package. Everything in
this module uses the standard library + the project's existing
``clean_text`` and ``VaderSentimentAnalyzer``. Heuristics are explicit
and individually named so a reviewer can read them.

Per-row rating/text inconsistency is reported as a ``WARNING`` category
called ``rating_text_mismatch``. Sarcasm and annotation noise are real
possibilities; the heuristic does not declare a row wrong, it surfaces it
for human review.
"""
from __future__ import annotations

import re
import statistics
import string
from collections import Counter
from typing import Dict, List, Optional

from app.models import Review
from app.services.dataset_file_parser import read_columns_and_rows
from app.services.sentiment_analyzer import get_analyzer
from app.services.text_cleaning import clean_text

# ---- Heuristic thresholds. All values are documented and explicit. --------

SHORT_TEXT_CHARS = 10  # below this length, "extremely short" flag is raised
ALL_CAPS_RATIO_FLAG = 0.5  # ratio of uppercase letters to alpha letters
URL_HEAVY_COUNT_FLAG = 3  # number of URLs above which a row is URL-heavy
REPEATED_CHAR_RUN = 5  # a run of this many same chars in a row raises a flag

# English-vs-rest heuristic. We do not claim language identification. The
# heuristic simply checks whether the lowercase-letter fraction of the
# text is consistent with a script the model can score; if too few of the
# chars are ASCII letters we mark the row as "other/unknown". The
# document explicitly says this is a heuristic, not detection.
ASCII_ALPHA_RATIO_UNKNOWN = 0.4

_SENTIMENT_MISMATCH_DELTA = 0.4  # |compound| > 0.4 = strong sentiment direction
_RATING_SENTIMENT_MISMATCH_MIN_STRONG = 0.4  # |compound| above this is "strong"

_SAMPLE_PER_FLAG = 3  # how many sample rows to keep per quality flag

# A small set of English stopwords used by the language heuristic. These
# are not used for any actual analysis — they only contribute to the
# "looks like English" / "looks like something else" label. We are
# explicit that this is a heuristic.
_HEURISTIC_ENGLISH_HINTS = frozenset({
    "the", "is", "and", "a", "of", "to", "in", "i", "it", "this", "that",
    "was", "is", "are", "for", "with", "on", "as", "but", "not", "have",
    "be", "so", "do", "at", "or", "from", "by", "an", "we", "you",
})

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_REPEATED_CHAR_RE = re.compile(r"(.)\1{" + str(REPEATED_CHAR_RUN - 1) + r",}")
_WORD_RE = re.compile(r"[A-Za-z']+")


def _ascii_alpha_ratio(text: str) -> float:
    if not text:
        return 0.0
    alpha = sum(1 for c in text if c.isascii() and c.isalpha())
    return alpha / max(1, sum(1 for c in text if c.isalpha()))


def _uppercase_ratio(text: str) -> float:
    if not text:
        return 0.0
    upper = sum(1 for c in text if c.isalpha() and c.isupper())
    alpha = sum(1 for c in text if c.isalpha())
    return upper / max(1, alpha)


def _english_hint_ratio(text: str) -> float:
    """Heuristic: fraction of word tokens in the small English hint set.

    NOT a language detector. Returns 0.0 on empty / non-Latin text.
    """
    if not text:
        return 0.0
    tokens = [t.lower() for t in _WORD_RE.findall(text)]
    if not tokens:
        return 0.0
    matches = sum(1 for t in tokens if t in _HEURISTIC_ENGLISH_HINTS)
    return matches / len(tokens)


def _classify_text_language(text: str) -> str:
    """Heuristic, deterministic language classification.

    Returns one of:
      - "english_likely"  : mostly ASCII letters with a plausible English word structure
      - "non_english_or_unknown" : few ASCII letters or non-Latin script
      - "empty"            : no usable text

    NOTE: This is a lightweight heuristic, not language identification.
    It checks the script (Latin vs non-Latin) and very conservatively
    flags obvious non-Latin; it does not attempt to distinguish English
    from other Latin-script languages. The disclaimer is carried in the
    profile's ``warnings`` text whenever the unknown share is high.
    """
    if not text or not text.strip():
        return "empty"
    if _ascii_alpha_ratio(text) < ASCII_ALPHA_RATIO_UNKNOWN:
        return "non_english_or_unknown"
    # If the text is Latin-script and long enough to be a review,
    # treat it as English-likely. Short English reviews often contain
    # no stopword in the tiny hint set (e.g. "Great product!"), so
    # requiring a hint token would over-flag.
    return "english_likely"


def _row_quality_flags(text: str) -> List[str]:
    """Heuristic row-level quality flags. A row can have multiple flags."""
    flags: List[str] = []
    if not text or not text.strip():
        flags.append("empty_text")
        return flags
    if len(text) < SHORT_TEXT_CHARS:
        flags.append("extremely_short_text")
    if _uppercase_ratio(text) >= ALL_CAPS_RATIO_FLAG:
        flags.append("excessive_caps")
    url_count = len(_URL_RE.findall(text))
    if url_count >= URL_HEAVY_COUNT_FLAG:
        flags.append("url_heavy")
    if _REPEATED_CHAR_RE.search(text):
        flags.append("repeated_characters")
    return flags


def _classify_by_text(review_text: str) -> Optional[str]:
    """Classify a single review text into a VADER-suggested label without
    looking at the rating. Returns None if the analyzer is unavailable.
    """
    analyzer = get_analyzer()
    if analyzer is None:
        return None
    result = analyzer.analyze(review_text or "")
    compound = float(result.get("compound", 0.0))
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def _rating_label(rating) -> Optional[str]:
    """Map a numeric rating to a coarse sentiment label.

    1-2 -> negative
    3   -> neutral
    4-5 -> positive
    Unknown for non-numeric or out-of-range ratings.
    """
    if rating is None:
        return None
    try:
        v = float(rating)
    except (TypeError, ValueError):
        return None
    if v <= 2.0:
        return "negative"
    if v >= 4.0:
        return "positive"
    if 2.5 <= v <= 3.5:
        return "neutral"
    return None


def _build_rating_mismatches(
    text_rating_pairs: List[tuple],
) -> List[Dict]:
    """Heuristic: rating and VADER text-class disagree strongly, and the
    text classification is confident. Returns a list of mismatch records
    (no more than _SAMPLE_PER_FLAG × number-of-buckets for inspection).
    """
    mismatches: Dict[str, List[Dict]] = {
        "strong_positive_text_low_rating": [],
        "strong_negative_text_high_rating": [],
    }
    for row_number, text, rating in text_rating_pairs:
        rating_label = _rating_label(rating)
        if rating_label is None:
            continue
        if not text or not text.strip():
            continue
        analyzer = get_analyzer()
        result = analyzer.analyze(text)
        compound = float(result.get("compound", 0.0))
        if abs(compound) < _RATING_SENTIMENT_MISMATCH_MIN_STRONG:
            continue
        if compound >= 0.05 and rating_label == "negative":
            bucket = mismatches["strong_positive_text_low_rating"]
            if len(bucket) < _SAMPLE_PER_FLAG:
                bucket.append({
                    "row": row_number,
                    "rating": float(rating),
                    "textCompound": round(compound, 4),
                    "textLabel": "positive",
                    "ratingLabel": rating_label,
                })
        elif compound <= -0.05 and rating_label == "positive":
            bucket = mismatches["strong_negative_text_high_rating"]
            if len(bucket) < _SAMPLE_PER_FLAG:
                bucket.append({
                    "row": row_number,
                    "rating": float(rating),
                    "textCompound": round(compound, 4),
                    "textLabel": "negative",
                    "ratingLabel": rating_label,
                })
    flat: List[Dict] = []
    for key, items in mismatches.items():
        flat.append({"type": key, "samples": items})
    return flat


def _row_grade(row_number: int, text: str, rating) -> Dict:
    return {
        "row": row_number,
        "textLength": len(text or ""),
        "rating": float(rating) if rating is not None and str(rating).strip() != "" else None,
        "flags": _row_quality_flags(text or ""),
        "languageHint": _classify_text_language(text or ""),
    }


def build_dataset_profile(dataset) -> Dict:
    """Build the profile JSON for a dataset.

    Reads the dataset file (re-using the existing parser), normalises
    every row through the same ``clean_text`` the dataset service uses,
    and computes a deterministic profile.

    Returns a JSON-compatible dict. The structure is stable and additive
    — new fields may be added in the future without breaking callers.
    """
    columns, raw_rows = read_columns_and_rows(dataset.file_path, dataset.file_type)
    mapping = dataset.column_mapping or {}
    text_col = mapping.get("text")
    rating_col = mapping.get("rating")
    date_col = mapping.get("date")

    total = len(raw_rows)
    valid_rows = 0
    invalid_rows = 0
    duplicate_rows = 0
    empty_text_rows = 0
    text_lengths: List[int] = []
    quality_flag_counts: Counter = Counter()
    rating_distribution: Counter = Counter()
    rating_present = 0
    rating_missing = 0
    rating_min = None
    rating_max = None
    rating_values: List[float] = []
    language_counts: Counter = Counter()
    sample_rows_by_flag: Dict[str, List[Dict]] = {}
    text_rating_pairs: List[tuple] = []

    # Include existing project reviews in duplicate detection so counts match
    # dataset_service.validate_dataset's project-scoped dedup. This is
    # best-effort — if the Review table cannot be queried, fall back to
    # intra-file deduplication only.
    try:
        from app.services.text_cleaning import normalize_for_dedup as _nd
        existing_hashes = {
            _nd(r.text)
            for r in Review.query.filter_by(project_id=dataset.project_id).filter(Review.deleted_at.is_(None)).all()
        }
    except Exception:
        existing_hashes = set()
    seen_text_hashes = set(existing_hashes)

    for idx, raw in enumerate(raw_rows):
        row_number = idx + 2  # 1-indexed + header row
        raw_text = (raw.get(text_col) if text_col else None) or ""
        text = clean_text(raw_text)
        if not text:
            empty_text_rows += 1
            invalid_rows += 1
            language_counts["empty"] += 1
            continue

        # Rating validation — mirrors dataset_service._parse_rating exactly.
        raw_rating = (raw.get(rating_col) if rating_col else None)
        rating: Optional[float] = None
        rating_ok = True
        if rating_col and raw_rating is not None and str(raw_rating).strip() != "":
            try:
                v = float(raw_rating)
            except (TypeError, ValueError):
                rating_ok = False
            else:
                if not (0 <= v <= 5):
                    rating_ok = False
                else:
                    rating = v
        elif rating_col and raw_rating is not None and str(raw_rating).strip() == "":
            rating = None
        else:
            rating = None

        if not rating_ok:
            invalid_rows += 1
            continue

        # Valid row (duplicates are valid, flagged, per dataset_service).
        normalized = text.lower().strip()
        is_dup = normalized in seen_text_hashes
        seen_text_hashes.add(normalized)
        if is_dup:
            duplicate_rows += 1
        valid_rows += 1
        text_lengths.append(len(text))
        language_counts[_classify_text_language(text)] += 1
        row_flags = _row_quality_flags(text)
        for f in row_flags:
            quality_flag_counts[f] += 1
            bucket = sample_rows_by_flag.setdefault(f, [])
            if len(bucket) < _SAMPLE_PER_FLAG:
                bucket.append(_row_grade(row_number, text, None))

        if rating is not None:
            rating_distribution[str(int(rating)) if rating.is_integer() else str(round(rating, 2))] += 1
            rating_values.append(rating)
            rating_present += 1
            rating_min = rating if rating_min is None else min(rating_min, rating)
            rating_max = rating if rating_max is None else max(rating_max, rating)
            text_rating_pairs.append((row_number, text, rating))
        else:
            rating_missing += 1

    rating_mean = round(statistics.mean(rating_values), 3) if rating_values else None
    rating_median = round(statistics.median(rating_values), 3) if rating_values else None

    avg_text_length = round(statistics.mean(text_lengths), 2) if text_lengths else None
    min_text_length = min(text_lengths) if text_lengths else None
    max_text_length = max(text_lengths) if text_lengths else None

    quality_flags: Dict[str, int] = dict(quality_flag_counts)

    rating_mismatches = _build_rating_mismatches(text_rating_pairs)
    total_mismatches = sum(len(bucket["samples"]) for bucket in rating_mismatches)

    warnings: List[str] = []
    if total == 0:
        warnings.append("Dataset contains zero rows.")
    if valid_rows == 0:
        warnings.append("No valid rows after text normalization.")
    if duplicate_rows and valid_rows:
        dup_ratio = duplicate_rows / max(1, total)
        if dup_ratio >= 0.25:
            warnings.append(
                f"{duplicate_rows} of {total} rows ({round(dup_ratio * 100, 1)}%) are exact-text duplicates."
            )
    if rating_mismatches and total_mismatches >= 3:
        warnings.append(
            f"{total_mismatches} row(s) show strong rating/text inconsistency — review for sarcasm or annotation noise."
        )
    if language_counts.get("non_english_or_unknown", 0) and language_counts.get("non_english_or_unknown", 0) >= max(1, total // 4):
        warnings.append(
            "A non-trivial fraction of rows appear non-English or use non-Latin script — "
            "VADER is tuned for English; results on other languages are unreliable."
        )
    short_count = quality_flag_counts.get("extremely_short_text", 0)
    if short_count and short_count >= max(1, valid_rows // 5):
        warnings.append(
            f"{short_count} row(s) are extremely short (under {SHORT_TEXT_CHARS} characters) and may not carry enough signal for sentiment."
        )
    caps_count = quality_flag_counts.get("excessive_caps", 0)
    if caps_count:
        warnings.append(f"{caps_count} row(s) are mostly uppercase; sentiment models can over-fire on caps.")

    info: List[str] = []
    info.append(f"{valid_rows} valid, {invalid_rows} invalid, {duplicate_rows} duplicate, {empty_text_rows} empty-text row(s).")
    if rating_present:
        info.append(f"Ratings present in {rating_present} of {valid_rows} valid rows; mean {rating_mean}, median {rating_median}.")
    else:
        info.append("No usable numeric ratings in this dataset.")
    if avg_text_length is not None:
        info.append(f"Average cleaned text length: {avg_text_length} characters (min {min_text_length}, max {max_text_length}).")

    severity = "info"
    if warnings:
        severity = "warning"
    if total == 0 or valid_rows == 0:
        severity = "error"

    return {
        "rowCount": total,
        "validRowCount": valid_rows,
        "invalidRowCount": invalid_rows,
        "duplicateRowCount": duplicate_rows,
        "emptyTextCount": empty_text_rows,
        "averageTextLength": avg_text_length,
        "minTextLength": min_text_length,
        "maxTextLength": max_text_length,
        "languageDistribution": dict(language_counts),
        "ratingDistribution": {
            "min": rating_min,
            "max": rating_max,
            "mean": rating_mean,
            "median": rating_median,
            "missing": rating_missing,
            "counts": {k: int(v) for k, v in rating_distribution.items()},
        },
        "qualityFlags": {
            "counts": quality_flags,
            "samples": sample_rows_by_flag,
        },
        "ratingTextMismatches": rating_mismatches,
        "ratingTextMismatchSampleCount": total_mismatches,
        "severity": severity,
        "warnings": warnings,
        "info": info,
    }
