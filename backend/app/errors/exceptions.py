class APIError(Exception):
    """Base class for application errors that map to a JSON error response."""

    code = "INTERNAL_ERROR"
    status_code = 500
    message = "An unexpected error occurred"

    def __init__(self, message=None, code=None, status_code=None, details=None):
        super().__init__(message or self.message)
        if message:
            self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}


class ValidationError(APIError):
    code = "VALIDATION_ERROR"
    status_code = 400
    message = "Request validation failed"


class UnauthenticatedError(APIError):
    code = "UNAUTHENTICATED"
    status_code = 401
    message = "Authentication is required"


class ForbiddenError(APIError):
    code = "FORBIDDEN"
    status_code = 403
    message = "You do not have permission to perform this action"


class NotFoundError(APIError):
    code = "NOT_FOUND"
    status_code = 404
    message = "Resource not found"


class ConflictError(APIError):
    code = "CONFLICT"
    status_code = 409
    message = "Resource already exists or conflicts with existing data"


class CollectionError(APIError):
    """Data-collection failures. `code` is always one of the stable
    COLLECTION_* taxonomy values (see app/services/collectors/errors.py) —
    the message is always a safe, user-facing string; raw exception details
    / stack traces never reach the client.
    """
    code = "COLLECTION_HTTP_ERROR"
    status_code = 422
    message = "Data collection failed"
