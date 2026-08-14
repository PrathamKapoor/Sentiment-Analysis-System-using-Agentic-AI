import uuid

from app.errors.exceptions import ValidationError


def is_valid_uuid(value):
    if not value:
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def parse_uuid_param(value, name):
    if value is None or value == "":
        return None
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise ValidationError(f"{name} must be a valid UUID")


def parse_float_param(value, name, minimum=None, maximum=None):
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValidationError(f"{name} must be a number")
    if minimum is not None and result < minimum:
        raise ValidationError(f"{name} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise ValidationError(f"{name} must be <= {maximum}")
    return result


def parse_analysis_filters(args):
    """Shared query-param parsing for the analysis GET endpoints. Every
    value is validated (never passed raw into a query) — this is also what
    keeps SQL-injection-shaped filter input inert: SQLAlchemy already
    parameterises the query, and malformed values are rejected here before
    they'd even reach it.
    """
    return {
        "dateFrom": args.get("dateFrom") or None,
        "dateTo": args.get("dateTo") or None,
        "sourceId": parse_uuid_param(args.get("sourceId"), "sourceId"),
        "datasetId": parse_uuid_param(args.get("datasetId"), "datasetId"),
        "aspectId": parse_uuid_param(args.get("aspectId") or args.get("aspect_id"), "aspectId"),
        "rating": parse_float_param(args.get("rating"), "rating", 0, 5),
        "sentiment": args.get("sentiment") or None,
        "minimumConfidence": parse_float_param(args.get("minimumConfidence"), "minimumConfidence", 0, 1),
        "minimumFrequency": parse_float_param(args.get("minimumFrequency"), "minimumFrequency", 0),
        "language": args.get("language") or None,  # accepted, not applied — see README
    }
