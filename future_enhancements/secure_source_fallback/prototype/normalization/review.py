from datetime import date

from ..models import NormalizedReview


def normalize_reviews(payload: list[dict], entity: str) -> list[NormalizedReview]:
    records = []
    for item in payload[:100]:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 10_000:
            continue
        payload_entity = item.get("entity")
        if payload_entity and entity.lower() not in str(payload_entity).lower() and str(payload_entity).lower() not in entity.lower():
            continue
        rating = item.get("rating")
        if rating is not None:
            try:
                rating = float(rating)
            except (ValueError, TypeError):
                continue
            if not 0 <= rating <= 5:
                continue
        reviewed_on = item.get("date")
        if reviewed_on is not None:
            try:
                reviewed_on = date.fromisoformat(str(reviewed_on))
            except ValueError:
                continue
        records.append(NormalizedReview(item.get("id"), text.strip(), item.get("reviewer"), rating, reviewed_on, item.get("url"), item.get("language"), {"source_record_type": "adapter_payload"}))
    return records
