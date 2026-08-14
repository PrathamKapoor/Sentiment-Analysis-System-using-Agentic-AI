from marshmallow import Schema, fields, validate

SOURCE_TYPES = ["review_site", "ecommerce", "reddit", "forum", "blog", "news", "survey"]


class CreateDataSourceSchema(Schema):
    type = fields.String(required=True, validate=validate.OneOf(SOURCE_TYPES))
    url = fields.String(required=True, validate=validate.Length(min=1))
    keywords = fields.List(fields.String(), load_default=list)


class UpdateDataSourceSchema(Schema):
    url = fields.String(validate=validate.Length(min=1))
    keywords = fields.List(fields.String())
    enabled = fields.Boolean()
