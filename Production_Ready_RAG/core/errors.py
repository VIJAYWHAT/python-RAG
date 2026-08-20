"""
Application exception types.

Each one carries a *safe* client-facing message. Handlers in
api/main.py turn these into HTTP responses; nothing else is ever
returned to a client, so internal details (stack traces, upstream
payloads, SQL) cannot leak.
"""


class AppError(Exception):
    """Base class. `message` is safe to show a user."""

    status_code = 500

    message = "An internal server error occurred."

    def __init__(self, message: str | None = None, *, detail: str | None = None):

        # `detail` is for the log only, never for the response.
        self.detail = detail

        if message:
            self.message = message

        super().__init__(self.detail or self.message)


class AuthenticationError(AppError):
    """The caller's token is missing, malformed, expired or revoked."""

    status_code = 401

    message = "Your session has expired. Please sign in again."


class AuthorizationError(AppError):
    """
    The caller is authenticated but asked for something that is not
    theirs. Raised when a request tries to act on an employee other
    than the one the token belongs to.
    """

    status_code = 403

    message = "You are not allowed to access this information."


class UpstreamUnavailableError(AppError):
    """The Ejadah API could not be reached or returned garbage."""

    status_code = 503

    message = (
        "The HR system is not responding at the moment. "
        "Please try again shortly."
    )


class RateLimitError(AppError):

    status_code = 429

    message = (
        "You have sent too many messages. "
        "Please wait a moment and try again."
    )


class ValidationError(AppError):

    status_code = 422

    message = "The request could not be processed."


class EmployeeRecordNotFoundError(AppError):

    status_code = 404

    message = "Your employee record could not be found in the HR system."
