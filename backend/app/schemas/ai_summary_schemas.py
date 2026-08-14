from marshmallow import Schema, fields, validate

from app.services.summary_service import SUMMARY_TYPES


class CreateSummarySchema(Schema):
    summaryType = fields.String(load_default="overall", validate=validate.OneOf(SUMMARY_TYPES))
    dateFrom = fields.Date(required=True)
    dateTo = fields.Date(required=True)


class UpdateSummarySchema(Schema):
    sections = fields.Dict(required=True)


class ApproveSummarySchema(Schema):
    editedContent = fields.Dict(required=False, allow_none=True)


class RejectSummarySchema(Schema):
    reason = fields.String(required=False, allow_none=True, validate=validate.Length(max=500))
