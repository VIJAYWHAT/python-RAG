"""
Health, readiness and maintenance.

`/health` is for the load balancer: cheap, unauthenticated, and it
says nothing about the internals.

`/ready` is for a deploy gate. It reports which subsystems answered,
so a bad rollout is visible before traffic arrives - but it is
behind the admin key, because "vector store empty, HR gateway
unreachable" is reconnaissance if it is public.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from api.container import Container, get_container
from api.dependencies import container, require_admin_key
from api.schemas import (
    HealthResponse,
    ReadinessResponse,
    SimpleStatusResponse,
)
from config.settings import settings
from core.logging_config import get_logger


logger = get_logger(__name__)

SERVICE_VERSION = "1.0.0"

router = APIRouter(tags=["operations"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe"
)
async def health() -> HealthResponse:

    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=SERVICE_VERSION
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe (admin key required)",
    dependencies=[Depends(require_admin_key)]
)
async def ready(
    deps: Container = Depends(container)
) -> ReadinessResponse:

    checks: dict = {}

    # ----------------------------------------------------------
    # Conversation store
    # ----------------------------------------------------------

    checks["chat_memory"] = (
        "ok"
        if await asyncio.to_thread(deps.memory_manager.ping)
        else "unavailable"
    )

    # ----------------------------------------------------------
    # Vector store
    # ----------------------------------------------------------

    try:
        count = await asyncio.to_thread(deps.vector_db.collection.count)

        checks["vector_store"] = (
            f"ok ({count} chunks)" if count else "empty"
        )

    except Exception as error:
        checks["vector_store"] = f"error: {type(error).__name__}"

    # ----------------------------------------------------------
    # Identity configuration
    # ----------------------------------------------------------

    from ejadah.identity_service import get_identity_service

    checks["identity"] = get_identity_service().identity_probe()

    checks["employee_data_source"] = settings.employee_data_source

    problems = settings.validate_for_production()

    checks["configuration"] = problems or "ok"

    degraded = (
        checks["chat_memory"] != "ok"
        or checks["vector_store"] == "empty"
        or bool(problems)
    )

    return ReadinessResponse(
        status="degraded" if degraded else "ready",
        checks=checks
    )


@router.post(
    "/api/admin/purge-memory",
    response_model=SimpleStatusResponse,
    summary="Apply the chat retention window now",
    dependencies=[Depends(require_admin_key)]
)
async def purge_memory(
    deps: Container = Depends(container)
) -> SimpleStatusResponse:

    deleted = await asyncio.to_thread(
        deps.memory_manager.purge_older_than,
        settings.memory_retention_days
    )

    logger.info(
        "Retention purge removed %s message(s) older than %s days",
        deleted,
        settings.memory_retention_days
    )

    return SimpleStatusResponse(
        detail=(
            f"Removed {deleted} message(s) older than "
            f"{settings.memory_retention_days} days."
        )
    )
