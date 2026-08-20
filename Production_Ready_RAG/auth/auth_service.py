"""
Authentication for the HR assistant.

There is no login here, and that is the point. The Ejadah app has
already authenticated the employee through `userLogin` (password,
OTP or biometric) and holds an `AccessToken`. This service accepts
that same token and nothing else, so:

  * there is no second password store to breach or keep in sync;
  * revoking a session in Ejadah revokes it here on the next call;
  * an employee cannot exist in the chatbot but not in HR.

The demo credential map that used to live in this file is gone.
It let anyone who knew `employee-001 / Test@123` read a seeded HR
record, which is fine for a laptop demo and unacceptable anywhere
else.

Everything real happens in ejadah/identity_service.py; this module
is the thin FastAPI-facing wrapper over it.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.errors import AppError, AuthenticationError
from core.logging_config import get_logger, mask_employee
from ejadah.identity_service import (
    Principal,
    get_identity_service,
)


logger = get_logger(__name__)


# auto_error=False so a missing header produces our own message
# rather than FastAPI's, and so the same handler covers both cases.
security = HTTPBearer(auto_error=False)


# The header the Flutter app uses to declare which employee it
# believes it is. It is a HINT ONLY - see identity_service.py. The
# value is checked against the token and the HR system, never
# trusted on its own.
EMPLOYEE_ID_HEADER = "X-Employee-Id"

SESSION_HEADER = "X-Session-Id"


class AuthService:

    # ==============================================================
    # Core
    # ==============================================================

    @staticmethod
    def authenticate_token(
        token: str,
        claimed_employee_id: Optional[str] = None
    ) -> Principal:
        """
        Verifies an Ejadah access token and returns the employee it
        belongs to.

        Raises AuthenticationError / AuthorizationError, which the
        app-wide handler turns into 401 / 403.
        """

        identity = get_identity_service()

        principal = identity.authenticate(
            token=token,
            claimed_employee_id=claimed_employee_id
        )

        identity.note_token_format(token)

        return principal

    @staticmethod
    def logout(token: str) -> bool:
        """
        Drops our cached view of the token.

        The Ejadah session itself is ended by the app calling
        Ejadah's own `logout`; this just makes sure we stop trusting
        the token immediately instead of waiting for the cache to
        expire.
        """

        if not token:
            return False

        get_identity_service().invalidate(token)

        return True

    # ==============================================================
    # FastAPI helpers
    # ==============================================================

    @classmethod
    def authenticate_request(
        cls,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials]
    ) -> Principal:

        if credentials is None or not credentials.credentials:

            raise HTTPException(
                status_code=401,
                detail="Missing or malformed Authorization header",
                headers={"WWW-Authenticate": "Bearer"}
            )

        claimed = request.headers.get(EMPLOYEE_ID_HEADER)

        try:
            return cls.authenticate_token(
                token=credentials.credentials,
                claimed_employee_id=claimed
            )

        except AppError as error:

            raise HTTPException(
                status_code=error.status_code,
                detail=error.message,
                headers=(
                    {"WWW-Authenticate": "Bearer"}
                    if error.status_code == 401
                    else None
                )
            ) from error

    # ==============================================================
    # Backwards-compatible shim
    # ==============================================================

    @classmethod
    def authenticate(
        cls,
        credentials: HTTPAuthorizationCredentials,
        claimed_employee_id: Optional[str] = None
    ) -> str:
        """
        Older call sites expected a bare employee id string.

        Prefer `authenticate_request`, which returns the full
        Principal - the token on it is needed to read HR data.
        """

        if not credentials or not credentials.credentials:

            raise HTTPException(
                status_code=401,
                detail="Missing authorization header"
            )

        try:
            principal = cls.authenticate_token(
                credentials.credentials,
                claimed_employee_id
            )

        except AppError as error:

            raise HTTPException(
                status_code=error.status_code,
                detail=error.message
            ) from error

        logger.debug(
            "Legacy authenticate() resolved employee=%s",
            mask_employee(principal.employee_id)
        )

        return principal.employee_id


__all__ = [
    "AuthService",
    "AuthenticationError",
    "EMPLOYEE_ID_HEADER",
    "SESSION_HEADER",
    "Principal",
    "security",
]
