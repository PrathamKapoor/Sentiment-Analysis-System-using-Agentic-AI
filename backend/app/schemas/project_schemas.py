from marshmallow import Schema, fields, validate


class CreateProjectSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=200))
    description = fields.String(required=False, allow_none=True)
    productOrTopic = fields.String(required=False, allow_none=True, validate=validate.Length(max=200))
    startDate = fields.Date(required=False, allow_none=True)
    endDate = fields.Date(required=False, allow_none=True)


class UpdateProjectSchema(Schema):
    name = fields.String(validate=validate.Length(min=1, max=200))
    description = fields.String(allow_none=True)
    productOrTopic = fields.String(allow_none=True, validate=validate.Length(max=200))
    startDate = fields.Date(allow_none=True)
    endDate = fields.Date(allow_none=True)


class AddProjectMemberSchema(Schema):
    userId = fields.String(required=True)


class ArchiveProjectSchema(Schema):
    archived = fields.Boolean(load_default=True)
