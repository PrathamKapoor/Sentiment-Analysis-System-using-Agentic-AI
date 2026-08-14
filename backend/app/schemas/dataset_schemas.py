from marshmallow import Schema, fields, validate


class MapColumnsSchema(Schema):
    text = fields.String(required=True)
    rating = fields.String(required=False, allow_none=True)
    date = fields.String(required=False, allow_none=True)
    source = fields.String(required=False, allow_none=True)
