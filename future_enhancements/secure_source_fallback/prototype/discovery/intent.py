import ipaddress
import re
from urllib.parse import unquote, urlparse

from ..errors import InvalidSourceError
from ..models import Capability, Intent

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "ref", "affid"}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_IGNORED = {"www", "product", "products", "p", "dp", "reviews", "review", "discussion", "discussions", "forum", "forums", "5g"}


def _safe_host(host: str) -> None:
    if not host:
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        raise InvalidSourceError("Private, loopback, link-local, and reserved hosts are not accepted.")


def _clean(value: str) -> str:
    value = unquote(value or "")
    if _CONTROL.search(value) or len(value) > 512:
        raise InvalidSourceError("Intent text contains control characters or exceeds the length limit.")
    value = re.sub(r"[-_/]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        raise InvalidSourceError("A non-empty topic or URL is required.")
    return value


def extract_intent(value: str, requested_source: str | None = None) -> Intent:
    if not isinstance(value, str):
        raise InvalidSourceError("A topic or URL string is required.")
    parsed = urlparse(value)
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"}:
            raise InvalidSourceError("Only HTTP(S) URLs are accepted as URL input.")
        _safe_host(parsed.hostname or "")
        host = (parsed.hostname or "").split(".")[0]
        segments = [unquote(p) for p in parsed.path.split("/") if p]
        tokens = [t for segment in segments for t in re.split(r"[-_]+", segment) if t and t.lower() not in _IGNORED]
        entity = _clean(" ".join(tokens[-8:]))
        source = requested_source or host or None
    else:
        entity, source = _clean(value), requested_source
    lower = entity.lower()
    category = "discussion" if any(word in lower for word in ("forum", "discussion", "reddit")) else "product"
    capabilities = (Capability.PUBLIC_DISCUSSION,) if category == "discussion" else (Capability.PRODUCT_REVIEWS, Capability.PRODUCT_DISCUSSION, Capability.PRODUCT_METADATA)
    return Intent(entity=entity.title(), category=category, requested_source=source, required_capabilities=capabilities)
