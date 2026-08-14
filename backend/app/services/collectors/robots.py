"""robots.txt compliance check — used before any HTML collection attempt.

Best-effort: if robots.txt is missing or unreachable, that's treated as
"allowed" (the overwhelming majority of sites have no robots.txt and mean
nothing by its absence). If it explicitly disallows our user agent (or all
agents) from the target path, we refuse — this is what backs
COLLECTION_NOT_PERMITTED and the "policy: blocked" preview field.
"""
import urllib.robotparser
from urllib.parse import urlparse, urlunparse

import requests

from app.services.collectors.security import validate_url_ssrf, ssrf_safe_connections


def _robots_txt_url(url):
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))


def is_collection_allowed_by_robots(url, limits):
    """Returns (allowed: bool, checked: bool). checked=False means robots.txt
    was unreachable/absent and `allowed` defaults to True (best-effort, not a
    guarantee of legal permission — see README compliance note).
    """
    robots_url = _robots_txt_url(url)
    try:
        validate_url_ssrf(robots_url)
        with ssrf_safe_connections():
            resp = requests.get(
                robots_url,
                timeout=limits.timeout_seconds,
                headers={"User-Agent": limits.user_agent},
                allow_redirects=False,
            )
    except Exception:
        return True, False

    if resp.status_code != 200:
        return True, False

    parser = urllib.robotparser.RobotFileParser()
    try:
        parser.parse(resp.text.splitlines())
    except Exception:
        return True, False

    return parser.can_fetch(limits.user_agent, url), True
