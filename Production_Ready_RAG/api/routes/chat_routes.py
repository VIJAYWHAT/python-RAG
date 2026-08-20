"""
Chat over REST.

Socket.IO is the primary transport for the app - it keeps the
connection warm and lets the server push the answer the moment it
is ready. These endpoints exist because a mobile app on a flaky
network needs a fallback that works over plain HTTPS, and because
history has to be fetchable when the socket is down.

`asyncio.to_thread` matters here: the pipeline is synchronous
(SQLite, the HTTP calls to Ejadah, the LLM SDK) and running it
directly in an async handler would block the event loop and stall
every other employee's request.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query

from api.container import Container
from api.dependencies import container, current_principal, enforce_rate_limit
from api.schemas import (
    ChatRequest,
    ChatResponseSchema,
    NewSessionResponse,
    SessionListResponse,
    SimpleStatusResponse,
    TranscriptResponse,
)
from core.logging_config import get_logger, mask_employee
from ejadah.identity_service import Principal
from session.session_manager import SessionManager


logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponseSchema,
    summary="Ask the HR assistant a question"
)
async def chat(
    request: ChatRequest,
    principal: Principal = Depends(enforce_rate_limit),
    deps: Container = Depends(container)
) -> ChatResponseSchema:

    session_id = SessionManager.validate(request.session_id)

    response = await asyncio.to_thread(
        deps.chat_service.ask,
        question=request.question,
        principal=principal,
        session_id=session_id
    )

    usage = response.llm_response

    return ChatResponseSchema(
        answer=response.answer,
        session_id=session_id,
        employee_id=principal.employee_id,
        guardrail_status=response.guardrail_status,
        guardrail_reason=response.guardrail_reason,
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None)
    )


@router.post(
    "/session",
    response_model=NewSessionResponse,
    summary="Start a new conversation thread"
)
async def new_session(
    principal: Principal = Depends(current_principal)
) -> NewSessionResponse:

    return NewSessionResponse(
        session_id=SessionManager.new_session_id(),
        employee_id=principal.employee_id
    )


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List this employee's conversation threads"
)
async def list_sessions(
    principal: Principal = Depends(current_principal),
    deps: Container = Depends(container),
    limit: int = Query(default=25, ge=1, le=100)
) -> SessionListResponse:

    rows = await asyncio.to_thread(
        deps.memory_manager.list_sessions,
        principal.employee_id,
        limit
    )

    # Storage keys are employee-scoped ("<employee>::<session>").
    # Hand back the bare session id the client gave us.
    prefix = f"{principal.employee_id.casefold()}::"

    for row in rows:

        stored = row.get("session_id") or ""

        if stored.startswith(prefix):
            row["session_id"] = stored[len(prefix):]

    return SessionListResponse(
        employee_id=principal.employee_id,
        sessions=rows
    )


@router.get(
    "/history",
    response_model=TranscriptResponse,
    summary="Fetch one conversation thread"
)
async def history(
    session_id: str = Query(..., max_length=100),
    principal: Principal = Depends(current_principal),
    deps: Container = Depends(container),
    limit: int = Query(default=100, ge=1, le=500)
) -> TranscriptResponse:

    clean_session = SessionManager.validate(session_id)

    # The lookup key is built from the VERIFIED employee number, so
    # passing another employee's session id returns an empty thread
    # rather than their messages.
    memory_key = SessionManager.scope(
        principal.employee_id,
        clean_session
    )

    messages = await asyncio.to_thread(
        deps.memory_manager.get_transcript,
        principal.employee_id,
        memory_key,
        limit
    )

    return TranscriptResponse(
        session_id=clean_session,
        employee_id=principal.employee_id,
        messages=messages
    )


@router.delete(
    "/history",
    response_model=SimpleStatusResponse,
    summary="Clear one conversation thread"
)
async def clear_history(
    session_id: str = Query(..., max_length=100),
    principal: Principal = Depends(current_principal),
    deps: Container = Depends(container)
) -> SimpleStatusResponse:

    clean_session = SessionManager.validate(session_id)

    memory_key = SessionManager.scope(
        principal.employee_id,
        clean_session
    )

    deleted = await asyncio.to_thread(
        deps.memory_manager.clear_session,
        principal.employee_id,
        memory_key
    )

    logger.info(
        "Cleared %s message(s) for employee=%s session=%s",
        deleted,
        mask_employee(principal.employee_id),
        clean_session
    )

    return SimpleStatusResponse(
        detail=f"Removed {deleted} message(s)."
    )
