from marshmallow import Schema, fields, validate


class CreateAspectVocabularySchema(Schema):
    canonicalName = fields.String(required=True, validate=validate.Length(min=1, max=150))
    surfaceForms = fields.List(fields.String(validate=validate.Length(min=1, max=150)), required=True, validate=validate.Length(min=1, max=50))


class UpdateAspectVocabularySchema(Schema):
    canonicalName = fields.String(required=False, allow_none=True, validate=validate.Length(min=1, max=150))
    surfaceForms = fields.List(fields.String(validate=validate.Length(min=1, max=150)), required=False, allow_none=True, validate=validate.Length(min=1, max=50))
    isActive = fields.Boolean(required=False, allow_none=True)
