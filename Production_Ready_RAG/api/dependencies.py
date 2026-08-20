"""
FastAPI dependencies.

`current_principal` is the single door every protected endpoint
goes through. Because it returns a `Principal` - which carries the
verified employee number AND the token needed to read that
employee's HR data - route handlers never see a raw employee id
string and never have to decide whose data to fetch.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from api.container import Container, get_container
from auth.auth_service import AuthService, security
from core.logging_config import get_logger, mask_employee
from ejadah.identity_service import Principal


logger = get_logger(__name__)


def container() -> Container:

    return get_container()


def current_principal(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Principal:

    principal = AuthService.authenticate_request(request, credentials)

    # Makes every log line for this request traceable to an
    # employee without re-verifying the token.
    request.state.employee_id = principal.employee_id

    return principal


def enforce_rate_limit(
    principal: Principal = Depends(current_principal),
    deps: Container = Depends(container)
) -> Principal:

    decision = deps.rate_limiter.evaluate(principal.employee_id)

    if not decision.allowed:

        logger.warning(
            "Rate limited employee=%s (retry in %ss)",
            mask_employee(principal.employee_id),
            decision.retry_after_seconds
        )

        raise HTTPException(
            status_code=429,
            detail=(
                "You have sent too many messages. Please wait a "
                "moment and try again."
            ),
            headers={
                "Retry-After": str(decision.retry_after_seconds)
            }
        )

    return principal


def require_admin_key(request: Request) -> None:
    """
    Guards the maintenance endpoints.

    Disabled unless ADMIN_API_KEY is set, so an unconfigured
    deployment does not expose them at all.
    """

    from config.settings import settings

    expected = (settings.admin_api_key or "").strip()

    if not expected:

        raise HTTPException(
            status_code=404,
            detail="Not found"
        )

    supplied = (request.headers.get("X-Admin-Key") or "").strip()

    import hmac

    if not supplied or not hmac.compare_digest(supplied, expected):

        logger.warning(
            "Rejected an admin request from %s",
            request.client.host if request.client else "unknown"
        )

        raise HTTPException(status_code=403, detail="Forbidden")
