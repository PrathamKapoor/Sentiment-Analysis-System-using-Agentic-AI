from marshmallow import Schema, fields, validate


class CreateInvestigationSchema(Schema):
    question = fields.String(required=True, validate=validate.Length(min=3, max=2000))
    idempotencyKey = fields.String(required=False, allow_none=True, validate=validate.Length(max=100))


class ReviewInvestigationFindingSchema(Schema):
    status = fields.String(required=True, validate=validate.OneOf(["ACCEPTED", "REJECTED"]))
    notes = fields.String(required=False, allow_none=True, validate=validate.Length(max=1000))
