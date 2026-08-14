from marshmallow import Schema, fields, validate

from app.models.alert import METRICS, OPERATORS, PRIORITIES


class CreateAlertSchema(Schema):
    name = fields.String(required=False, allow_none=True, validate=validate.Length(max=150))
    metric = fields.String(required=True, validate=validate.OneOf(METRICS))
    operator = fields.String(required=True, validate=validate.OneOf(OPERATORS))
    threshold = fields.Float(required=True)
    timeWindowDays = fields.Integer(required=False, allow_none=True, validate=validate.Range(min=1, max=365))
    keyword = fields.String(required=False, allow_none=True)
    aspectName = fields.String(required=False, allow_none=True)
    priority = fields.String(required=False, validate=validate.OneOf(PRIORITIES))
    enabled = fields.Boolean(required=False)


class UpdateAlertSchema(Schema):
    name = fields.String(allow_none=True, validate=validate.Length(max=150))
    metric = fields.String(validate=validate.OneOf(METRICS))
    operator = fields.String(validate=validate.OneOf(OPERATORS))
    threshold = fields.Float()
    timeWindowDays = fields.Integer(allow_none=True, validate=validate.Range(min=1, max=365))
    keyword = fields.String(allow_none=True)
    aspectName = fields.String(allow_none=True)
    priority = fields.String(validate=validate.OneOf(PRIORITIES))


class AssignAlertSchema(Schema):
    userId = fields.String(required=True)


class ResolveAlertSchema(Schema):
    resolutionNotes = fields.String(required=True, validate=validate.Length(min=1, max=2000))
