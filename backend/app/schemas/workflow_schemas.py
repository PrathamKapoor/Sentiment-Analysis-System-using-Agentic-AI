from marshmallow import Schema, fields, validate

from app.models.agent_workflow import WORKFLOW_TYPES


class StartWorkflowOptionsSchema(Schema):
    collectNewData = fields.Boolean(required=False, allow_none=True)
    runSentiment = fields.Boolean(required=False, allow_none=True)
    runTopics = fields.Boolean(required=False, allow_none=True)
    runAspects = fields.Boolean(required=False, allow_none=True)
    generateSummary = fields.Boolean(required=False, allow_none=True)
    generateRecommendations = fields.Boolean(required=False, allow_none=True)
    evaluateAlerts = fields.Boolean(required=False, allow_none=True)
    generateReport = fields.Boolean(required=False, allow_none=True)
    # Per-agent overrides (e.g. {"topic": {"topicCount": 5}, "report": {"fileFormat": "excel"}}).
    # Values are plain data (numbers/strings/booleans), never code — same
    # "selectors are data, not code" rule Phase 6 established for collectors.
    stepOptions = fields.Dict(keys=fields.String(), required=False, allow_none=True)


class StartWorkflowSchema(Schema):
    workflowType = fields.String(required=True, validate=validate.OneOf(WORKFLOW_TYPES))
    options = fields.Nested(StartWorkflowOptionsSchema, load_default=dict)
    idempotencyKey = fields.String(required=False, allow_none=True, validate=validate.Length(max=100))


class RejectWorkflowSchema(Schema):
    reason = fields.String(required=False, allow_none=True, validate=validate.Length(max=500))
