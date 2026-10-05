from marshmallow import Schema, fields, validate


class ProductDiscoveryRequestSchema(Schema):
    description = fields.String(required=True, validate=validate.Length(min=2, max=500))
    sku = fields.String(allow_none=True, validate=validate.Length(max=120))
    canonicalUrl = fields.String(allow_none=True, validate=validate.Length(max=2048))
    identifiers = fields.Dict(
        keys=fields.String(validate=validate.Length(min=1, max=80)),
        values=fields.String(validate=validate.Length(min=1, max=200)),
        validate=validate.Length(max=50),
    )
