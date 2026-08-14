from marshmallow import ValidationError as MarshmallowValidationError
from werkzeug.exceptions import HTTPException

from app.errors.exceptions import APIError
from app.utils.responses import error_response


def register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(err):
        return error_response(err.code, err.message, err.status_code, err.details)

    @app.errorhandler(MarshmallowValidationError)
    def handle_marshmallow_error(err):
        return error_response(
            "VALIDATION_ERROR",
            "Request validation failed",
            400,
            details=err.messages,
        )

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        code_map = {
            400: "VALIDATION_ERROR",
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "NOT_FOUND",
            409: "CONFLICT",
            429: "RATE_LIMITED",
        }
        return error_response(
            code_map.get(err.code, "INTERNAL_ERROR"),
            err.description or "Request failed",
            err.code or 500,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(err):
        app.logger.exception("Unhandled exception")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", 500)
