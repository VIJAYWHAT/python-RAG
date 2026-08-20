"""
Identity endpoints.

There is deliberately no `/api/login`. The Ejadah app logs the
employee in against Ejadah's own `userLogin` and already holds an
`AccessToken`; introducing a second credential store here would
mean a second thing to breach and a second thing to keep in sync
with HR.

What the app calls instead:

  GET  /api/me      once, after login, to confirm the chatbot
                    accepts its token and to greet the employee
  POST /api/logout  on sign-out, so the server stops trusting the
                    token immediately and drops the employee's
                    server-side conversation history
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from api.container import Container
from api.dependencies import container, current_principal
from api.schemas import MeResponse, SimpleStatusResponse
from auth.auth_service import AuthService
from core.logging_config import get_logger, mask_employee
from ejadah.identity_service import Principal


logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["identity"])


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Who does this token belong to?"
)
async def me(
    principal: Principal = Depends(current_principal)
) -> MeResponse:

    return MeResponse(
        employee_id=principal.employee_id,
        name=principal.employee_name,
        designation=principal.designation,
        department=principal.department,
        verified_by=list(principal.verified_by)
    )


@router.post(
    "/logout",
    response_model=SimpleStatusResponse,
    summary="Stop trusting this token and forget the conversation"
)
async def logout(
    principal: Principal = Depends(current_principal),
    deps: Container = Depends(container)
) -> SimpleStatusResponse:

    employee_id = principal.employee_id

    AuthService.logout(principal.token)

    # A shared device is the normal case for field staff, so the
    # employee's transcripts go with them rather than waiting for
    # the retention window.
    deleted = await asyncio.to_thread(
        deps.memory_manager.clear_user,
        employee_id
    )

    try:
        deps.employee_context_provider.invalidate(employee_id)

    except Exception as error:

        logger.warning(
            "Could not clear the cached HR data for employee=%s: %s",
            mask_employee(employee_id),
            error
        )

    deps.rate_limiter.reset(employee_id)

    logger.info(
        "Signed out employee=%s | removed %s stored message(s)",
        mask_employee(employee_id),
        deleted
    )

    return SimpleStatusResponse(
        detail=f"Signed out. Removed {deleted} stored message(s)."
    )
