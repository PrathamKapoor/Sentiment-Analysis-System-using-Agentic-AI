from marshmallow import Schema, fields, validate


class CreateRoleSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    permissionCodes = fields.List(fields.String(), load_default=list)


class UpdateRoleSchema(Schema):
    name = fields.String(validate=validate.Length(min=1, max=100))
    permissionCodes = fields.List(fields.String())


class AssignRoleSchema(Schema):
    roleId = fields.String(required=True)
