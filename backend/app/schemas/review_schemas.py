from marshmallow import Schema, fields, validate


class UpdateReviewSchema(Schema):
    text = fields.String(validate=validate.Length(min=1))
    rating = fields.Float(allow_none=True, validate=validate.Range(min=0, max=5))
    reviewDate = fields.Date(allow_none=True)
    source = fields.String(allow_none=True)
    isSpam = fields.Boolean()
    isDuplicate = fields.Boolean()


class MarkSpamSchema(Schema):
    isSpam = fields.Boolean(load_default=True)
