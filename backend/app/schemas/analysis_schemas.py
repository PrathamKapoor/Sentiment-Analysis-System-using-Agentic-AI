from marshmallow import Schema, fields, validate

from app.models.sentiment_result import LABELS


class RunSentimentAnalysisSchema(Schema):
    includeSpam = fields.Boolean(load_default=False)
    includeDuplicates = fields.Boolean(load_default=False)


class CorrectSentimentSchema(Schema):
    label = fields.String(required=True, validate=validate.OneOf(LABELS))
    reason = fields.String(required=False, allow_none=True, validate=validate.Length(max=500))


class RunTopicAnalysisSchema(Schema):
    topicCount = fields.Integer(required=False, allow_none=True, validate=validate.Range(min=1, max=50))


class RunAspectAnalysisSchema(Schema):
    includeSpam = fields.Boolean(load_default=False)
    includeDuplicates = fields.Boolean(load_default=False)


class ComparisonSchema(Schema):
    targetProjectIds = fields.List(fields.String(), required=True, validate=validate.Length(min=2))
    dateFrom = fields.Date(required=False, allow_none=True)
    dateTo = fields.Date(required=False, allow_none=True)
