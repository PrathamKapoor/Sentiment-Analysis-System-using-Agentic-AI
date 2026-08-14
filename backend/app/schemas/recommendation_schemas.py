from marshmallow import Schema, fields, validate

from app.models.recommendation import PRIORITIES


class GenerateRecommendationsSchema(Schema):
    minFrequency = fields.Integer(required=False, allow_none=True, validate=validate.Range(min=1))


class UpdateRecommendationSchema(Schema):
    text = fields.String(validate=validate.Length(min=1))
    priority = fields.String(validate=validate.OneOf(PRIORITIES))


class AssignRecommendationSchema(Schema):
    userId = fields.String(required=True)
