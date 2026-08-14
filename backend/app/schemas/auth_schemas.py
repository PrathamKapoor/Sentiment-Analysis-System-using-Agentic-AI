from marshmallow import Schema, fields, validate, pre_load


class _NormalisedIdentitySchema(Schema):
    @pre_load
    def normalize_identity_fields(self, data, **kwargs):
        """Keep account identity stable before validation and persistence."""
        data = dict(data or {})
        for field in ("email", "name", "organisationName"):
            if isinstance(data.get(field), str):
                data[field] = data[field].strip()
        if isinstance(data.get("email"), str):
            data["email"] = data["email"].lower()
        return data


class RegisterSchema(_NormalisedIdentitySchema):
    organisationName = fields.String(required=True, validate=validate.Length(min=1, max=200))
    email = fields.Email(required=True)
    password = fields.String(required=True, validate=validate.Length(min=10, max=128))
    name = fields.String(required=True, validate=validate.Length(min=1, max=150))


class LoginSchema(_NormalisedIdentitySchema):
    email = fields.Email(required=True)
    password = fields.String(required=True)
