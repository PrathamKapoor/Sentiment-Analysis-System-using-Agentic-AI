import re

_WHITESPACE_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(raw_text):
    """Basic text cleaning: strip HTML tags, collapse whitespace, trim.

    ponytail: naive tag stripping (not a full HTML parser) and whitespace
    collapsing — enough for Phase 2 ingestion hygiene. Upgrade to a proper
    normalizer (unicode NFKC, emoji handling, language-aware) if/when the
    sentiment-analysis phase needs cleaner input.
    """
    if raw_text is None:
        return ""
    text = _HTML_TAG_RE.sub(" ", str(raw_text))
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def normalize_for_dedup(text):
    """Lowercased, whitespace-collapsed form used only for duplicate comparison."""
    return clean_text(text).lower()
