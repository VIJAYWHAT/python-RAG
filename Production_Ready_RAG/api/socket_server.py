"""
Socket.IO transport.

The handshake is where authentication happens, once, per
connection:

    io(url, { auth: { token: <AccessToken>, employee_id: <id> } })

`connect` verifies the token and stores the resolved employee on
the socket session. From then on every `chat` event uses THAT
employee - the payload of an individual message cannot change who
the answer is about, because the message payload is never consulted
for identity. A client that reconnects with a different token gets
a different socket and a fresh verification.

Sessions are held server-side by python-socketio, keyed by socket
id, so nothing about the identity travels with each message.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import socketio

from api.container import get_container
from auth.auth_service import AuthService
from config.settings import settings
from core.errors import AppError, AuthenticationError, AuthorizationError
from core.logging_config import get_logger, mask_employee, mask_token
from ejadah.identity_service import Principal
from session.session_manager import SessionManager


logger = get_logger(__name__)


sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=(
        settings.socket_cors_allow_origins
        if settings.socket_cors_allow_origins
        else []
    ),
    logger=False,
    engineio_logger=False,
    ping_interval=25,
    ping_timeout=60,
    # Cap the payload so a client cannot push a huge frame at us.
    max_http_buffer_size=256 * 1024
)


# Event names the client listens for.
EVENT_READY = "chat_ready"
EVENT_RESPONSE = "chat_response"
EVENT_ERROR = "chat_error"
EVENT_TYPING = "chat_typing"
EVENT_SESSION_CLEARED = "chat_session_cleared"


# ==================================================================
# Connection lifecycle
# ==================================================================


@sio.event
async def connect(sid: str, environ: Dict[str, Any], auth):

    token, claimed_employee = _read_handshake(auth)

    if not token:

        logger.info("Socket %s rejected: no token in the handshake", sid)

        # Raising ConnectionRefusedError lets the client see a
        # reason instead of a bare disconnect.
        raise socketio.exceptions.ConnectionRefusedError(
            "Authentication required"
        )

    try:

        principal = await asyncio.to_thread(
            AuthService.authenticate_token,
            token,
            claimed_employee
        )

    except AuthorizationError as error:

        logger.warning(
            "Socket %s refused: %s",
            sid,
            error.detail or error.message
        )

        raise socketio.exceptions.ConnectionRefusedError(
            error.message
        ) from error

    except AuthenticationError as error:

        logger.info(
            "Socket %s refused: invalid token %s",
            sid,
            mask_token(token)
        )

        raise socketio.exceptions.ConnectionRefusedError(
            error.message
        ) from error

    except AppError as error:

        logger.error(
            "Socket %s refused: %s",
            sid,
            error.detail or error.message
        )

        raise socketio.exceptions.ConnectionRefusedError(
            error.message
        ) from error

    except Exception as error:  # pragma: no cover

        logger.exception("Socket %s refused: unexpected error", sid)

        raise socketio.exceptions.ConnectionRefusedError(
            "Unable to establish a secure session"
        ) from error

    await sio.save_session(
        sid,
        {
            "principal": principal,
            # A default thread so a client that never sends a
            # session_id still gets continuity within the socket.
            "session_id": SessionManager.new_session_id(),
        }
    )

    logger.info(
        "Socket %s connected | employee=%s verified_by=%s",
        sid,
        mask_employee(principal.employee_id),
        "+".join(principal.verified_by)
    )

    await sio.emit(
        EVENT_READY,
        {
            "employee_id": principal.employee_id,
            "name": principal.employee_name,
            "designation": principal.designation,
            "department": principal.department,
        },
        to=sid
    )


@sio.event
async def disconnect(sid: str):

    logger.info("Socket %s disconnected", sid)


# ==================================================================
# Chat
# ==================================================================


@sio.event
async def chat(sid: str, data: Any):

    principal = await _principal_for(sid)

    if principal is None:
        return

    if not isinstance(data, dict):

        await _fail(sid, "The message could not be read.")
        return

    question = str(data.get("question") or "").strip()

    if not question:

        await _fail(sid, "Please type a question first.")
        return

    if len(question) > settings.max_question_length:

        await _fail(
            sid,
            f"Please shorten your question to "
            f"{settings.max_question_length} characters or fewer."
        )
        return

    deps = get_container()

    # ----------------------------------------------------------
    # Rate limit
    # ----------------------------------------------------------

    decision = deps.rate_limiter.evaluate(principal.employee_id)

    if not decision.allowed:

        logger.warning(
            "Rate limited employee=%s on socket %s",
            mask_employee(principal.employee_id),
            sid
        )

        await _fail(
            sid,
            "You've sent a lot of messages just now. Please wait "
            f"{decision.retry_after_seconds} seconds and try again.",
            code="rate_limited",
            retry_after=decision.retry_after_seconds
        )
        return

    # ----------------------------------------------------------
    # Session thread
    # ----------------------------------------------------------

    try:
        session_id = SessionManager.validate(data.get("session_id"))

    except AppError as error:

        await _fail(sid, error.message)
        return

    await _remember_session(sid, session_id)

    await sio.emit(EVENT_TYPING, {"typing": True}, to=sid)

    # ----------------------------------------------------------
    # Answer
    # ----------------------------------------------------------

    try:

        response = await asyncio.to_thread(
            deps.chat_service.ask,
            question=question,
            principal=principal,
            session_id=session_id
        )

    except AuthenticationError as error:

        # The Ejadah token died mid-conversation. Tell the client so
        # it can send the employee back to the login screen, then
        # close the socket.
        logger.info(
            "Token expired mid-conversation for employee=%s",
            mask_employee(principal.employee_id)
        )

        await _fail(
            sid,
            error.message,
            code="unauthorized",
            session_id=session_id
        )

        await sio.disconnect(sid)
        return

    except AppError as error:

        logger.error(
            "Chat failed for employee=%s: %s",
            mask_employee(principal.employee_id),
            error.detail or error.message
        )

        await _fail(sid, error.message, session_id=session_id)
        return

    except Exception:  # pragma: no cover

        logger.exception(
            "Unhandled chat error for employee=%s",
            mask_employee(principal.employee_id)
        )

        await _fail(
            sid,
            "Something went wrong while preparing your answer. "
            "Please try again.",
            session_id=session_id
        )
        return

    finally:

        await sio.emit(EVENT_TYPING, {"typing": False}, to=sid)

    usage = response.llm_response

    await sio.emit(
        EVENT_RESPONSE,
        {
            "answer": response.answer,
            "session_id": session_id,
            "employee_id": principal.employee_id,
            "guardrail_status": response.guardrail_status,
            "guardrail_reason": response.guardrail_reason,
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(
                usage, "completion_tokens", None
            ),
            "total_tokens": getattr(usage, "total_tokens", None),
        },
        to=sid
    )

    logger.info(
        "Answered employee=%s session=%s status=%s tokens=%s",
        mask_employee(principal.employee_id),
        session_id,
        response.guardrail_status,
        getattr(usage, "total_tokens", None)
    )


@sio.event
async def clear_session(sid: str, data: Any):
    """
    Called when the employee taps "New chat".

    Clears the server-side transcript for that one thread, so the
    next question is not answered with context from the last one.
    """

    principal = await _principal_for(sid)

    if principal is None:
        return

    payload = data if isinstance(data, dict) else {}

    try:
        session_id = SessionManager.validate(payload.get("session_id"))

    except AppError as error:

        await _fail(sid, error.message)
        return

    deps = get_container()

    memory_key = SessionManager.scope(
        principal.employee_id,
        session_id
    )

    deleted = await asyncio.to_thread(
        deps.memory_manager.clear_session,
        principal.employee_id,
        memory_key
    )

    new_session_id = SessionManager.new_session_id()

    await _remember_session(sid, new_session_id)

    logger.info(
        "Cleared session %s for employee=%s (%s message(s))",
        session_id,
        mask_employee(principal.employee_id),
        deleted
    )

    await sio.emit(
        EVENT_SESSION_CLEARED,
        {
            "cleared_session_id": session_id,
            "session_id": new_session_id,
            "removed": deleted,
        },
        to=sid
    )


# ==================================================================
# Helpers
# ==================================================================


def _read_handshake(auth) -> tuple[Optional[str], Optional[str]]:
    """
    Pulls the token and the (advisory) employee id out of the
    handshake.

    Only the `auth` payload is read. Query-string tokens are
    ignored on purpose: URLs end up in proxy logs, and a token in a
    log is a token that has leaked.
    """

    if not isinstance(auth, dict):
        return None, None

    token = auth.get("token") or auth.get("access_token")

    employee_id = (
        auth.get("employee_id")
        or auth.get("employeeId")
        or auth.get("EmployeeId")
    )

    token = str(token).strip() if token else None

    employee_id = str(employee_id).strip() if employee_id else None

    return token or None, employee_id or None


async def _principal_for(sid: str) -> Optional[Principal]:

    try:
        session = await sio.get_session(sid)

    except KeyError:
        session = None

    principal = (session or {}).get("principal")

    if isinstance(principal, Principal):
        return principal

    logger.info("Socket %s has no verified session; disconnecting", sid)

    await _fail(
        sid,
        "Your session has expired. Please sign in again.",
        code="unauthorized"
    )

    await sio.disconnect(sid)

    return None


async def _remember_session(sid: str, session_id: str) -> None:

    try:
        session = await sio.get_session(sid)

    except KeyError:
        return

    session["session_id"] = session_id

    await sio.save_session(sid, session)


async def _fail(
    sid: str,
    message: str,
    code: str = "error",
    **extra
) -> None:

    payload = {"message": message, "code": code}

    payload.update(
        {
            key: value
            for key, value in extra.items()
            if value is not None
        }
    )

    await sio.emit(EVENT_ERROR, payload, to=sid)
