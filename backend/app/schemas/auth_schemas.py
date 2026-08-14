from marshmallow import Schema, fields, validate


class RegisterSchema(Schema):
    organisationName = fields.String(required=True, validate=validate.Length(min=1, max=200))
    email = fields.Email(required=True)
    password = fields.String(required=True, validate=validate.Length(min=10, max=128))
    name = fields.String(required=True, validate=validate.Length(min=1, max=150))


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True)
