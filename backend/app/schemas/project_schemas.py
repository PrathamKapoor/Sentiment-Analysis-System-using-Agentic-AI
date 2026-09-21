from marshmallow import Schema, fields, validate


class CreateProjectSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=200))
    description = fields.String(required=False, allow_none=True)
    productOrTopic = fields.String(required=False, allow_none=True, validate=validate.Length(max=200))
    startDate = fields.Date(required=False, allow_none=True)
    endDate = fields.Date(required=False, allow_none=True)
    # Optional public business-context URL. Setting it on creation is
    # allowed; the URL is only fetched when the user explicitly requests
    # a refresh or generates an enhanced report. Shape is checked here;
    # SSRF is checked at extraction time.
    websiteUrl = fields.String(required=False, allow_none=True, validate=validate.Length(max=2048))


class UpdateProjectSchema(Schema):
    name = fields.String(validate=validate.Length(min=1, max=200))
    description = fields.String(allow_none=True)
    productOrTopic = fields.String(allow_none=True, validate=validate.Length(max=200))
    startDate = fields.Date(allow_none=True)
    endDate = fields.Date(allow_none=True)
    # Setting websiteUrl to "" or null clears it. The actual write goes
    # through project_website_service so the cached context is dropped
    # at the same time.
    websiteUrl = fields.String(allow_none=True, validate=validate.Length(max=2048))


class AddProjectMemberSchema(Schema):
    userId = fields.String(required=True)


class ArchiveProjectSchema(Schema):
    archived = fields.Boolean(load_default=True)
