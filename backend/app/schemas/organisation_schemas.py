from marshmallow import Schema, fields, validate


class UpdateOrganisationSchema(Schema):
    name = fields.String(validate=validate.Length(min=1, max=200))
    plan = fields.String(validate=validate.OneOf(["free", "pro", "enterprise"]))


class InviteMemberSchema(Schema):
    email = fields.Email(required=True)
    roleIds = fields.List(fields.String(), required=False, load_default=list)


class UpdateMemberSchema(Schema):
    status = fields.String(validate=validate.OneOf(["invited", "active", "inactive"]))
