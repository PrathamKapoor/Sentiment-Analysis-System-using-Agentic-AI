from marshmallow import Schema, fields, validate

from app.models.report import FILE_FORMATS, REPORT_MODES
from app.services.report_data_service import ALL_SECTIONS


class CreateReportSchema(Schema):
    reportName = fields.String(required=False, allow_none=True, validate=validate.Length(max=200))
    dateFrom = fields.Date(required=True)
    dateTo = fields.Date(required=True)
    sections = fields.List(fields.String(validate=validate.OneOf(ALL_SECTIONS)), load_default=list)
    fileFormat = fields.String(required=True, validate=validate.OneOf(FILE_FORMATS))
    # ``standard`` (default): deterministic findings only, no LLM ever.
    # ``enhanced``: deterministic findings + optional AI-Generated
    # Contextual Interpretation when an LLM is configured. The two modes
    # never differ on measured numbers; they only differ on whether the
    # AI section is included.
    mode = fields.String(load_default="standard", validate=validate.OneOf(REPORT_MODES))
    includeAiSummary = fields.Boolean(load_default=False)
    includeRecommendations = fields.Boolean(load_default=False)
    includeRepresentativeReviews = fields.Boolean(load_default=False)
