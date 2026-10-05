from marshmallow import Schema, fields, validate


_KEYWORD = fields.String(validate=validate.Length(min=1, max=100))


class ProjectEntitySchema(Schema):
    brand = fields.String(allow_none=True, validate=validate.Length(max=120))
    product = fields.String(allow_none=True, validate=validate.Length(max=200))
    model = fields.String(allow_none=True, validate=validate.Length(max=120))
    sku = fields.String(allow_none=True, validate=validate.Length(max=120))
    canonicalUrl = fields.String(allow_none=True, validate=validate.Length(max=2048))
    aliases = fields.List(
        fields.String(validate=validate.Length(min=1, max=200)),
        validate=validate.Length(max=50),
    )
    identifiers = fields.Dict(
        keys=fields.String(validate=validate.Length(min=1, max=80)),
        values=fields.String(validate=validate.Length(min=1, max=200)),
        validate=validate.Length(max=50),
    )
    includeKeywords = fields.List(_KEYWORD, validate=validate.Length(max=50))
    excludeKeywords = fields.List(_KEYWORD, validate=validate.Length(max=50))
    securityKeywords = fields.List(_KEYWORD, validate=validate.Length(max=50))
    competitorKeywords = fields.List(_KEYWORD, validate=validate.Length(max=50))
    customKeywords = fields.List(_KEYWORD, validate=validate.Length(max=50))
