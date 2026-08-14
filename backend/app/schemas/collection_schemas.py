from marshmallow import Schema, fields, validate

_SELECTOR_FIELDS = (
    "review_container_selector", "review_text_selector",
    "reviewer_selector", "rating_selector", "date_selector",
)


class SelectorOverrideSchema(Schema):
    """Selectors are plain CSS strings (data), never code — see
    app/services/collectors/static_html.py module docstring.
    """
    review_container_selector = fields.String(required=True, validate=validate.Length(min=1, max=300))
    review_text_selector = fields.String(validate=validate.Length(max=300))
    reviewer_selector = fields.String(validate=validate.Length(max=300))
    rating_selector = fields.String(validate=validate.Length(max=300))
    date_selector = fields.String(validate=validate.Length(max=300))


class PreviewSourceSchema(Schema):
    selectors = fields.Nested(SelectorOverrideSchema, required=False, allow_none=True)


class CollectSourceSchema(Schema):
    selectors = fields.Nested(SelectorOverrideSchema, required=False, allow_none=True)
    maxPages = fields.Integer(required=False, validate=validate.Range(min=1, max=100))
    maxRecords = fields.Integer(required=False, validate=validate.Range(min=1, max=5000))
