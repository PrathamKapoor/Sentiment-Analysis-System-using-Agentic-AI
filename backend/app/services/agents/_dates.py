"""Small shared helper — not a public agent, just avoids duplicating the
same date-range-resolution logic in summary_agent.py and report_agent.py.
"""
from datetime import date, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import Review

_FALLBACK_WINDOW_DAYS = 365


def _as_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))  # workflow options arrive as JSON strings over HTTP


def resolve_date_range(project_id, params):
    """Explicit dateFrom/dateTo in params win. Otherwise use the project's
    actual review date span (never fabricated), falling back to a wide
    window only if no dated reviews exist at all.
    """
    date_from = _as_date(params.get("dateFrom"))
    date_to = _as_date(params.get("dateTo"))
    if date_from and date_to:
        return date_from, date_to

    bounds = (
        db.session.query(func.min(Review.review_date), func.max(Review.review_date))
        .filter(Review.project_id == project_id, Review.deleted_at.is_(None))
        .first()
    )
    min_date, max_date = (bounds or (None, None))
    today = date.today()

    date_from = date_from or min_date or (today - timedelta(days=_FALLBACK_WINDOW_DAYS))
    date_to = date_to or max_date or today
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    return date_from, date_to
